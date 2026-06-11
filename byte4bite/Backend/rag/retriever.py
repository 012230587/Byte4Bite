"""
MySQL-backed RAG retriever for Byte4Bite.

Data flow:
  user query  →  gemini-embedding-001 (768-d query vector)
             →  RecipeRepository.keyword_search() (cheap pre-filter)
             →  RecipeRepository.vector_search() (numpy cosine on VARBINARY blobs)
             →  top-k recipe dicts  →  ai_service.generate_new_recipe_from_query()
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional, Union

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from database.recipe_repository import RecipeRepository
from rag.embeddings import embed_text
from services.text_consolidation import normalize_recipe_payload

STOP_WORDS = {
    "and", "or", "with", "a", "the", "of", "for", "in", "to", "from", "by", "on", "is", "at", "as",
}

# Below this cosine similarity, retrieval confidence is considered low (Phase E).
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.42"))

PdfPath = Union[str, Path]


def _words_to_column_text(words: list[dict[str, Any]]) -> str:
    """Rebuild one column's text by reading words top-to-bottom, left-to-right."""
    if not words:
        return ""

    line_buckets: dict[float, list[dict[str, Any]]] = {}
    for word in sorted(words, key=lambda w: (w.get("top", 0), w.get("x0", 0))):
        bucket = round(float(word.get("top", 0)) / 3) * 3
        line_buckets.setdefault(bucket, []).append(word)

    lines: list[str] = []
    for bucket in sorted(line_buckets.keys()):
        row_words = sorted(line_buckets[bucket], key=lambda w: w.get("x0", 0))
        line = " ".join(str(w.get("text", "")).strip() for w in row_words if w.get("text"))
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _extract_page_columns_pdfplumber(page: Any) -> str:
    """
    Column-aware page extraction: read column 1 vertically, then column 2.
    Avoids horizontal reads that merge '3/4 cup pecans' with 'toasted'.
    """
    words = page.extract_words(
        x_tolerance=2,
        y_tolerance=3,
        keep_blank_chars=False,
        use_text_flow=False,
    ) or []
    if not words:
        return (page.extract_text(layout=True) or page.extract_text() or "").strip()

    page_width = float(page.width)
    page_height = float(page.height)
    mid_x = page_width / 2.0
    gutter = max(8.0, page_width * 0.02)

    left_words = [w for w in words if float(w.get("x1", 0)) <= mid_x - gutter]
    right_words = [w for w in words if float(w.get("x0", 0)) >= mid_x + gutter]

    # Single-column page: both sides populated across full width, or right column empty.
    two_column = (
        len(left_words) >= 8
        and len(right_words) >= 8
        and len(right_words) >= len(left_words) * 0.2
    )
    if not two_column:
        return (page.extract_text(layout=True) or page.extract_text() or "").strip()

    left_bbox = (0, 0, mid_x - gutter, page_height)
    right_bbox = (mid_x + gutter, 0, page_width, page_height)

    left_text = (page.crop(left_bbox).extract_text(layout=True) or "").strip()
    right_text = (page.crop(right_bbox).extract_text(layout=True) or "").strip()

    if not left_text:
        left_text = _words_to_column_text(left_words)
    if not right_text:
        right_text = _words_to_column_text(right_words)

    if left_text and right_text:
        return f"{left_text}\n\n{right_text}"
    return left_text or right_text


def _extract_page_columns_pypdf(page: Any) -> str:
    """Fallback column split using pypdf layout extraction + wide-gap line repair."""
    layout_text = ""
    try:
        layout_text = page.extract_text(extraction_mode="layout") or ""
    except TypeError:
        layout_text = page.extract_text() or ""
    except Exception:
        layout_text = page.extract_text() or ""

    if not layout_text.strip():
        return ""

    lines = [line.strip() for line in layout_text.splitlines() if line.strip()]
    if len(lines) < 4:
        return layout_text.strip()

    # Heuristic: lines with a wide internal gap were read across two columns.
    repaired: list[str] = []
    for line in lines:
        parts = [part.strip() for part in re.split(r" {4,}|\t", line) if part.strip()]
        if len(parts) == 2:
            repaired.append(parts[0])
            repaired.append(parts[1])
        else:
            repaired.append(line)
    return "\n".join(repaired)


def extract_text_from_pdf(pdf_path: PdfPath) -> str:
    """
    Extract recipe text from a PDF with column-aware layout processing.

    Two-column recipe PDFs are read column-by-column (left top-to-bottom, then right)
    instead of blind horizontal extraction that scrambles ingredients with descriptors
    like 'toasted' or 'split'.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    pages: list[str] = []

    try:
        import pdfplumber
    except ImportError:
        pdfplumber = None

    if pdfplumber is not None:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                page_text = _extract_page_columns_pdfplumber(page)
                if page_text.strip():
                    pages.append(page_text.strip())
        if pages:
            return "\n\n".join(pages)

    try:
        from pypdf import PdfReader
    except ImportError as exc:
        if pdfplumber is None:
            raise ImportError(
                "PDF extraction requires pdfplumber or pypdf. "
                "Install with: pip install pdfplumber pypdf"
            ) from exc
        return "\n\n".join(pages)

    reader = PdfReader(str(path))
    for page in reader.pages:
        page_text = _extract_page_columns_pypdf(page)
        if page_text.strip():
            pages.append(page_text.strip())

    return "\n\n".join(pages)


def invalidate_embedding_cache() -> None:
    """No-op kept for backward compatibility with memory_service cache invalidation."""
    return None


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    normalized = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in text)
    tokens = [token for token in normalized.split() if token not in STOP_WORDS]
    return " ".join(tokens)


def _embed_query(text: str):
    """Embed the user query with the shared embedding model (768-dim, L2-normalized)."""
    try:
        return embed_text(text.strip())
    except Exception as exc:
        print(f"DEBUG: query embedding failed: {exc}")
        return None


def _exact_title_match(query: str) -> list[dict]:
    """Fast path: exact title hit from keyword search with full-string match."""
    candidates = RecipeRepository.keyword_search(query, limit=20)
    query_norm = _normalize_text(query)
    return [
        recipe for recipe in candidates
        if _normalize_text(recipe.get("title", "")) == query_norm
    ]


def _normalize_results(recipes: list[dict]) -> list[dict]:
    """Ensure RAG context recipes have consolidated ingredient lists."""
    return [normalize_recipe_payload(recipe) for recipe in recipes]


def find_best_recipes_scored(
    user_query: str,
    top_k: int = 5,
) -> tuple[list[dict], Optional[str]]:
    """
    Hybrid retrieval with similarity scores and optional low-confidence note.
    Returns (recipes, retrieval_note).
    """
    query = (user_query or "").strip()
    if not query:
        pool = RecipeRepository.fetch_all(limit=top_k)
        normalized = _normalize_results(pool)
        for recipe in normalized:
            recipe["search_mode"] = "browse"
        return normalized, None

    total = RecipeRepository.count()
    if total == 0:
        print("DEBUG: asian_recipes table is empty — run: python -m rag.ingest")
        return [], "Recipe corpus is empty. Ingest datasets first."

    print(f"DEBUG: RAG querying MySQL corpus ({total} recipes) for: {query!r}")

    exact = _exact_title_match(query)
    if exact:
        results = _normalize_results(exact[:top_k])
        for recipe in results:
            recipe["search_mode"] = "browse"
            recipe["similarity_score"] = 1.0
        return results, None

    query_vec = _embed_query(query)
    if query_vec is not None:
        scored = RecipeRepository.vector_search_scored(query_vec, limit=top_k)
        if scored:
            top_score = scored[0][0]
            results = _normalize_results([recipe for _, recipe in scored])
            note = None
            if top_score < SIMILARITY_THRESHOLD:
                note = (
                    "Limited semantic matches in the corpus; results are best-effort. "
                    "Try Generate for a tailored recipe."
                )
            print(f"DEBUG: vector search returned {len(results)} recipes (top={top_score:.3f})")
            return results, note

    keyword_hits = RecipeRepository.keyword_search(query, limit=top_k)
    if keyword_hits:
        results = _normalize_results(keyword_hits[:top_k])
        for recipe in results:
            recipe["search_mode"] = "keyword"
        return results, "Keyword matches only — semantic index unavailable for this query."

    print("DEBUG: no vector/keyword hits; returning recent recipes")
    fallback = _normalize_results(RecipeRepository.fetch_all(limit=top_k))
    for recipe in fallback:
        recipe["search_mode"] = "fallback"
    return fallback, "No close matches found; showing recent corpus recipes."


def find_best_recipes(user_query: str, top_k: int = 3) -> list[dict]:
    """Retrieve the most relevant recipes from MySQL using hybrid vector-first search."""
    recipes, _note = find_best_recipes_scored(user_query, top_k=top_k)
    return recipes


def find_recipes_for_ingredients(ingredients_str: str, top_k: int = 5) -> list[dict]:
    """Context retrieval for the LLM generator — same hybrid MySQL search."""
    return find_best_recipes(ingredients_str, top_k=top_k)
