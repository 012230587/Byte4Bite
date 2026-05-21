try:
    from google import genai
except Exception:
    genai = None
import pandas as pd
import numpy as np
import os

# 1. Setup the Client
API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY) if (genai is not None and API_KEY) else None

# Get the absolute path to the datasets directory
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASETS_DIR = os.path.join(BACKEND_DIR, "datasets")

# Cache for embeddings to avoid repeated API calls
_EMBEDDING_CACHE = {}

STOP_WORDS = {
    'and', 'or', 'with', 'a', 'the', 'of', 'for', 'in', 'to', 'from', 'by', 'on', 'is', 'at', 'as'
}


def invalidate_embedding_cache():
    global _EMBEDDING_CACHE
    _EMBEDDING_CACHE = {}


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    normalized = ''.join(ch.lower() if ch.isalnum() or ch.isspace() else ' ' for ch in text)
    tokens = [token for token in normalized.split() if token not in STOP_WORDS]
    return ' '.join(tokens)


def _keyword_search(query: str, recipes: list, top_k: int = 10) -> list:
    query_lower = query.lower().strip()
    if not query_lower:
        return recipes[:top_k]

    scored = []
    for recipe in recipes:
        score = 0
        title = recipe.get('title', '').lower()
        description = recipe.get('description', '').lower()
        ingredients = ' '.join(recipe.get('ingredients', [])).lower()
        instructions = ' '.join(recipe.get('instructions', [])).lower()
        if query_lower in title:
            score += 5
        if query_lower in description:
            score += 3
        if query_lower in ingredients:
            score += 4
        if query_lower in instructions:
            score += 2
        if score > 0:
            scored.append((score, recipe))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [recipe for _, recipe in scored[:top_k]]


def _exact_title_matches(query: str, recipes: list) -> list:
    query_normalized = _normalize_text(query)
    if not query_normalized:
        return []
    return [
        recipe for recipe in recipes
        if _normalize_text(recipe.get('title', '')) == query_normalized
    ]


def _embed_text(text: str):
    try:
        vec = np.array(client.models.embed_content(
            model='models/gemini-embedding-2',
            contents=text
        ).embeddings[0].values)
        norm = np.linalg.norm(vec)
        if norm == 0 or np.isnan(norm):
            return vec
        return vec / norm
    except Exception as e:
        print(f"DEBUG: embedding failed: {e}")
        return np.zeros(768)


def find_best_recipes(user_query: str, top_k: int = 3):
    """
    Semantic search across all recipe datasets using embeddings.
    Returns the top_k most semantically similar recipes.
    Only returns recipes that pass data integrity validation.
    """
    # Get all recipes from the loaded datasets
    from services import recipe_service
    all_recipes = recipe_service._load_all_recipes()

    # Filter for validated recipes only
    validated_recipes = [r for r in all_recipes if recipe_service._validate_recipe_integrity(r)]

    if not validated_recipes:
        print("DEBUG: No validated recipes available for RAG search")
        return []

    print(f"DEBUG: RAG searching across {len(validated_recipes)} validated recipes (filtered from {len(all_recipes)} total)")

    exact_matches = _exact_title_matches(user_query, validated_recipes)
    if exact_matches:
        return exact_matches[:top_k]

    candidate_recipes = _keyword_search(user_query, validated_recipes, top_k=50)
    if not candidate_recipes:
        print("DEBUG: No keyword candidates found, falling back to validated default recipes")
        return validated_recipes[:top_k]

    try:
        query_embedding = _embed_text(user_query)
    except Exception as e:
        print(f"DEBUG: Error embedding query: {e}")
        query_embedding = None

    # If embedding failed, fall back to keyword candidates
    if query_embedding is None or (isinstance(query_embedding, np.ndarray) and not query_embedding.any()):
        return candidate_recipes[:top_k]

    results = []
    for recipe in candidate_recipes:
        try:
            recipe_key = f"{recipe.get('title', 'unknown').strip().lower()}|{'|'.join([str(i).strip().lower() for i in recipe.get('ingredients', [])])}"
            if recipe_key not in _EMBEDDING_CACHE:
                text_to_embed = f"{recipe.get('title', '')} {recipe.get('description', '')} {' '.join(recipe.get('ingredients', []))} {recipe.get('instructions', '')}"
                _EMBEDDING_CACHE[recipe_key] = _embed_text(text_to_embed)

            row_embedding = _EMBEDDING_CACHE[recipe_key]
            # Ensure row_embedding is normalized; use dot which equals cosine for unit vectors
            score = float(np.dot(query_embedding, row_embedding))
            results.append((score, recipe))
        except Exception as e:
            print(f"DEBUG: Error embedding candidate {recipe.get('title', 'unknown')}: {e}")
            continue

    if not results:
        return candidate_recipes[:top_k]

    results.sort(key=lambda x: x[0], reverse=True)
    semantic_matches = [item[1] for item in results[:top_k]]

    unique_matches = []
    seen_titles = set()
    # Merge semantic and candidate lists preserving top semantic matches first
    for recipe in semantic_matches + candidate_recipes:
        title_lower = recipe.get('title', '').lower()
        if title_lower not in seen_titles:
            unique_matches.append(recipe)
            seen_titles.add(title_lower)
        if len(unique_matches) >= top_k:
            break

    print(f"DEBUG: RAG found {len(unique_matches)} matching recipes")
    return unique_matches


def find_recipes_for_ingredients(ingredients_str: str, top_k: int = 5):
    """
    Find recipes that are most similar to user-provided ingredients.
    Used to provide context for AI recipe generation.
    """
    return find_best_recipes(ingredients_str, top_k=top_k)
