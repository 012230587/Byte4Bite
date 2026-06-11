"""
Recipe service — vector-first browse and RAG-backed compose modes.
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
        stats = RecipeRepository.count_embedding_stats()
        print(
            f"DEBUG: MySQL asian_recipes corpus: {count} rows "
            f"(embeddings valid={stats['valid_embeddings']})"
        )
        if count < MIN_DB_RECIPES:
            print("DEBUG: Low recipe count — run: python -m rag.ingest")
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


def _get_search_corpus() -> list[dict]:
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


def _apply_restriction_filter(recipes: list[dict], restrictions: list[str]) -> list[dict]:
    if not restrictions:
        return recipes
    return [
        recipe for recipe in recipes
        if dataset_search.matches_dietary_restrictions(recipe, restrictions)
    ]


def _vector_browse(query: str, restrictions: list[str], limit: int = 20) -> list[dict]:
    """Phase B: vector-first ranked browse of existing corpus recipes."""
    semantic, _note = retriever.find_best_recipes_scored(query, top_k=limit * 2)
    filtered = _apply_restriction_filter(semantic, restrictions)
    ranked = dataset_search.search_and_rank(filtered, query, restrictions, limit=limit)
    print(f"DEBUG: browse mode query={query!r} -> {len(ranked)} vector-ranked results")
    return [_normalize_output_recipe(r) for r in ranked]


_validate_recipe_integrity = dataset_search.validate_recipe


def get_personalized_recipes(
    query: Optional[str] = None,
    restrictions: Optional[list[str]] = None,
):
    """
    Browse mode (GET /api/recipes): return up to 20 existing corpus recipes.
    Uses vector-first ranking when embeddings are available.
    """
    normalized_restrictions = _normalize_restrictions(restrictions)

    try:
        RecipeRepository.log_search(
            user_id=None,
            query_text=query or "",
            search_mode="browse",
        )
    except Exception:
        pass

    if not query:
        corpus = _get_search_corpus()
        results = dataset_search.search_and_rank(corpus, None, normalized_restrictions, limit=20)
        output = [_normalize_output_recipe(r) for r in results]
        for recipe in output:
            recipe.setdefault("search_mode", "browse")
        return output

    embed_stats = RecipeRepository.count_embedding_stats()
    if embed_stats.get("valid_embeddings", 0) > 0 and RecipeRepository.count() >= MIN_DB_RECIPES:
        return _vector_browse(query, normalized_restrictions)

    candidates: list[dict] = []
    try:
        if RecipeRepository.count() > 0:
            candidates = RecipeRepository.keyword_search(query, limit=500)
    except Exception as exc:
        print(f"DEBUG: keyword_search failed: {exc}")

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
    output = [_normalize_output_recipe(r) for r in results]
    for recipe in output:
        recipe.setdefault("search_mode", "keyword")
    return output


def compose_recipe_from_query(
    query: str,
    restrictions: Optional[list[str]] = None,
    cuisine: Optional[str] = None,
) -> dict:
    """
    Compose mode (POST /api/recipes/generate): one tailored AI recipe from vector context.
    """
    normalized_restrictions = _normalize_restrictions(restrictions)

    try:
        RecipeRepository.log_search(
            user_id=None,
            query_text=query,
            search_mode="compose",
        )
    except Exception:
        pass

    result = ai_service.generate_new_recipe_from_query(
        query,
        None,
        normalized_restrictions,
        cuisine=cuisine,
    )
    return result


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
