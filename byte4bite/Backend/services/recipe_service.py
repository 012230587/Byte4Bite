"""
Recipe service — search over MySQL corpus with CSV fallback when DB is sparse.
"""

from __future__ import annotations

from typing import Optional

from database.recipe_repository import RecipeRepository
from rag import retriever
from services import dataset_search
from services.text_consolidation import instructions_look_fragmented, normalize_recipe_payload
from . import ai_service

_CSV_CACHE: list[dict] | None = None
MIN_DB_RECIPES = 50


def invalidate_recipe_cache() -> None:
    global _CSV_CACHE
    _CSV_CACHE = None


def preload_recipes() -> None:
    try:
        count = RecipeRepository.count()
        print(f"DEBUG: MySQL asian_recipes corpus: {count} rows")
        if count < MIN_DB_RECIPES:
            print("DEBUG: Low recipe count — run: python -m rag.ingest --no-embed")
    except Exception as exc:
        print(f"DEBUG: Could not load recipe corpus: {exc}")


def _load_csv_corpus() -> list[dict]:
    global _CSV_CACHE
    if _CSV_CACHE is not None:
        return _CSV_CACHE
    from rag.csv_utils import iter_all_dataset_recipes
    _CSV_CACHE = iter_all_dataset_recipes()
    print(f"DEBUG: Loaded {_CSV_CACHE and len(_CSV_CACHE)} recipes from CSV fallback")
    return _CSV_CACHE or []


def _load_all_recipes() -> list[dict]:
    count = RecipeRepository.count()
    if count >= MIN_DB_RECIPES:
        return RecipeRepository.fetch_search_pool()
    return _load_csv_corpus()


def _get_search_corpus() -> list[dict]:
    """Prefer MySQL; merge CSV if database is still sparse."""
    db_count = RecipeRepository.count()
    if db_count >= MIN_DB_RECIPES:
        return RecipeRepository.fetch_search_pool()
    csv_recipes = _load_csv_corpus()
    if db_count == 0:
        return csv_recipes
    db_recipes = RecipeRepository.fetch_search_pool(limit=db_count + 500)
    seen = {r["title"].lower() for r in db_recipes}
    for recipe in csv_recipes:
        if recipe["title"].lower() not in seen:
            db_recipes.append(recipe)
    return db_recipes


def _normalize_output_recipe(recipe: dict) -> dict:
    normalized = normalize_recipe_payload(dict(recipe))
    instructions = normalized.get("instructions", [])

    # Layer 1: regex sanitization already applied in normalize_recipe_payload.
    # Layer 2: LLM stitching when steps still look like newline/timing fragments.
    if instructions_look_fragmented(instructions):
        try:
            stitched = ai_service.stitch_recipe_instructions_with_llm(
                normalized.get("title", "Recipe"),
                instructions,
            )
            if stitched:
                normalized["instructions"] = stitched
        except Exception as exc:
            print(f"DEBUG: LLM instruction stitch skipped: {exc}")

    try:
        normalized["instructions"] = ai_service._normalize_cooking_steps(normalized)
    except Exception as exc:
        print(f"DEBUG: Failed to normalize instructions: {exc}")
        if not isinstance(normalized.get("instructions"), list):
            normalized["instructions"] = ai_service._split_instruction_steps(
                str(normalized.get("instructions", ""))
            )
    return normalized


def _normalize_restrictions(restrictions: Optional[list[str]] = None) -> list[str]:
    if not restrictions:
        return []
    normalized = []
    for restriction in restrictions:
        if not isinstance(restriction, str):
            continue
        value = restriction.strip().lower()
        if value in {"gluten free", "gluten_free"}:
            value = "gluten-free"
        if value in {"vegetarian", "vegan", "halal", "gluten-free"} and value not in normalized:
            normalized.append(value)
    return normalized


# Re-export for backward compatibility
_validate_recipe_integrity = dataset_search.validate_recipe


def get_personalized_recipes(query: Optional[str] = None, restrictions: Optional[list[str]] = None):
    normalized_restrictions = _normalize_restrictions(restrictions)

    try:
        RecipeRepository.log_search(user_id=None, query_text=query or "")
    except Exception:
        pass

    if not query:
        corpus = _get_search_corpus()
        results = dataset_search.search_and_rank(corpus, None, normalized_restrictions, limit=20)
        return [_normalize_output_recipe(r) for r in results]

    candidates: list[dict] = []

    # 1. MySQL keyword pull (fast pre-filter per ingredient term)
    try:
        if RecipeRepository.count() > 0:
            candidates = RecipeRepository.keyword_search(query, limit=500)
    except Exception as exc:
        print(f"DEBUG: keyword_search failed: {exc}")

    # 2. RAG semantic boost when embeddings exist
    try:
        if RecipeRepository.count() >= MIN_DB_RECIPES:
            semantic = retriever.find_best_recipes(query, top_k=30)
            seen = {c.get("title", "").lower() for c in candidates}
            for recipe in semantic:
                key = recipe.get("title", "").lower()
                if key and key not in seen:
                    candidates.append(recipe)
                    seen.add(key)
    except Exception as exc:
        print(f"DEBUG: semantic search skipped: {exc}")

    # 3. Full corpus fallback when keyword/RAG returned little
    if len(candidates) < 5:
        corpus = _get_search_corpus()
        terms = dataset_search.parse_ingredient_terms(query)
        if terms:
            for recipe in corpus:
                if dataset_search.recipe_matches_ingredients(recipe, terms):
                    candidates.append(recipe)
        else:
            candidates.extend(corpus)

    results = dataset_search.search_and_rank(
        candidates, query, normalized_restrictions, limit=20
    )
    print(f"DEBUG: search query={query!r} restrictions={normalized_restrictions} -> {len(results)} results")
    return [_normalize_output_recipe(r) for r in results]


def get_personalized_recommendation(query: str, restrictions: Optional[list[str]] = None):
    normalized_restrictions = _normalize_restrictions(restrictions)
    matches = get_personalized_recipes(query, normalized_restrictions)

    if not matches:
        return {
            "ai_chat_response": "I couldn't find a matching recipe. Try different ingredients or generate a new one.",
            "recipe_details": None,
        }

    top_recipe = matches[0]
    ai_comment = ai_service.adjust_recipe_for_restrictions(top_recipe, normalized_restrictions)
    return {
        "ai_chat_response": ai_comment,
        "recipe_details": _normalize_output_recipe(top_recipe),
    }
