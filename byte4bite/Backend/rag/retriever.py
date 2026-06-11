"""
MySQL-backed RAG retriever for Byte4Bite.

Data flow (replaces in-memory CSV loading):
  user query  →  text-embedding-004 (query vector)
             →  RecipeRepository.keyword_search() (cheap pre-filter)
             →  RecipeRepository.vector_search() (numpy cosine on VARBINARY blobs)
             →  top-k recipe dicts  →  ai_service.generate_new_recipe_from_query()
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

try:
    from google import genai
except ImportError:
    genai = None

from database.recipe_repository import RecipeRepository, EMBEDDING_DIMENSION
from services.text_consolidation import normalize_recipe_payload

API_KEY = os.getenv("GEMINI_API_KEY")
EMBEDDING_MODEL = "text-embedding-004"
client = genai.Client(api_key=API_KEY) if (genai is not None and API_KEY) else None

STOP_WORDS = {
    "and", "or", "with", "a", "the", "of", "for", "in", "to", "from", "by", "on", "is", "at", "as",
}

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


def _embed_query(text: str) -> Optional[np.ndarray]:
    """Embed the user query with text-embedding-004 (768-dim, L2-normalized)."""
    if client is None:
        return None
    try:
        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text.strip(),
        )
        vec = np.array(response.embeddings[0].values, dtype=np.float32)
        if vec.shape[0] != EMBEDDING_DIMENSION:
            print(f"DEBUG: unexpected embedding dim {vec.shape[0]}")
            return None
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec
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


def find_best_recipes(user_query: str, top_k: int = 3) -> list[dict]:
    """
    Retrieve the most relevant recipes from MySQL using hybrid search:
      1. Exact title match (if any)
      2. Keyword pre-filter on title/description/ingredients JSON
      3. Vector cosine ranking on `asian_recipes.embedding`
    """
    query = (user_query or "").strip()
    if not query:
        return _normalize_results(RecipeRepository.fetch_all(limit=top_k))

    total = RecipeRepository.count()
    if total == 0:
        print("DEBUG: asian_recipes table is empty — run: python -m rag.ingest")
        return []

    print(f"DEBUG: RAG querying MySQL corpus ({total} recipes) for: {query!r}")

    exact = _exact_title_match(query)
    if exact:
        return _normalize_results(exact[:top_k])

    keyword_hits = RecipeRepository.keyword_search(query, limit=50)
    if not keyword_hits:
        print("DEBUG: no keyword hits; returning recent recipes")
        return _normalize_results(RecipeRepository.fetch_all(limit=top_k))

    query_vec = _embed_query(query)
    if query_vec is None:
        return _normalize_results(keyword_hits[:top_k])

    candidate_ids = [r["id"] for r in keyword_hits if r.get("id")]
    vector_hits = RecipeRepository.vector_search(
        query_vec,
        limit=top_k,
        candidate_ids=candidate_ids or None,
    )

    if vector_hits:
        print(f"DEBUG: vector search returned {len(vector_hits)} recipes")
        return _normalize_results(vector_hits[:top_k])

    return _normalize_results(keyword_hits[:top_k])


def find_recipes_for_ingredients(ingredients_str: str, top_k: int = 5) -> list[dict]:
    """Context retrieval for the LLM generator — same hybrid MySQL search."""
    return find_best_recipes(ingredients_str, top_k=top_k)
