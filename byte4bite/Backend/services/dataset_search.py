"""
Ingredient + dietary search logic shared by MySQL and CSV corpus.

Matches comma-separated pantry items (any term can match) and ranks by how many
ingredients hit. Dietary filters use exclusion rules on ingredient text when
recipes lack explicit dietary_tags (most dataset rows).
"""

from __future__ import annotations

import re
from typing import Optional

# Exclusion keywords for dietary restrictions (checked in ingredients + title)
MEAT_TERMS = {
    "chicken", "beef", "pork", "lamb", "mutton", "fish", "salmon", "tuna", "cod",
    "shrimp", "prawn", "bacon", "ham", "turkey", "sausage", "meat", "steak",
    "duck", "anchovy", "crab", "lobster", "oyster",
}
PORK_TERMS = {"pork", "bacon", "ham", "lard", "gelatin", "prosciutto"}
DAIRY_EGG_TERMS = {"milk", "cheese", "butter", "cream", "yogurt", "egg", "eggs", "ghee", "whey"}
GLUTEN_TERMS = {"wheat", "flour", "bread", "pasta", "noodle", "barley", "rye", "semolina", "couscous"}
ALCOHOL_TERMS = {"wine", "beer", "rum", "vodka", "whiskey", "sake", "mirin", "brandy", "liqueur"}


def parse_ingredient_terms(query: str) -> list[str]:
    """Split 'chicken, garlic, coconut milk' into searchable terms."""
    if not query:
        return []
    raw = re.split(r"[,;]+", query)
    terms = [t.strip().lower() for t in raw if t.strip()]
    if terms:
        return terms
    tokens = [t.lower() for t in re.findall(r"[A-Za-z]+", query) if len(t) > 2]
    return tokens


def _recipe_text(recipe: dict) -> str:
    parts = [
        str(recipe.get("title", "")),
        str(recipe.get("description", "")),
        " ".join(str(i) for i in recipe.get("ingredients", [])),
        " ".join(str(i) for i in recipe.get("instructions", [])),
    ]
    return " ".join(parts).lower()


def _term_matches(text: str, term: str) -> bool:
    if not term:
        return False
    if " " in term:
        return term in text
    if re.search(rf"\b{re.escape(term)}\b", text):
        return True
    return term in text


def ingredient_match_score(recipe: dict, terms: list[str]) -> int:
    if not terms:
        return 0
    text = _recipe_text(recipe)
    return sum(1 for term in terms if _term_matches(text, term))


def recipe_matches_ingredients(recipe: dict, terms: list[str]) -> bool:
    """True if at least one pantry ingredient appears in the recipe."""
    if not terms:
        return True
    return ingredient_match_score(recipe, terms) > 0


def _has_any_term(text: str, terms: set[str]) -> bool:
    for term in terms:
        if _term_matches(text, term):
            return True
    return False


def matches_dietary_restrictions(recipe: dict, restrictions: Optional[list[str]] = None) -> bool:
    """
    Filter by dietary needs. Uses explicit tags when present, otherwise checks
    ingredient text for prohibited items.
    """
    if not restrictions:
        return True

    text = _recipe_text(recipe)
    tags = {str(t).lower() for t in recipe.get("dietary_tags", []) if t}

    for restriction in restrictions:
        r = restriction.lower()
        if r == "vegetarian":
            if "vegan" in tags or "vegetarian" in tags:
                continue
            if _has_any_term(text, MEAT_TERMS):
                return False
        elif r == "vegan":
            if "vegan" in tags:
                continue
            if _has_any_term(text, MEAT_TERMS | DAIRY_EGG_TERMS):
                return False
        elif r == "halal":
            if "halal" in tags:
                continue
            if _has_any_term(text, PORK_TERMS | ALCOHOL_TERMS):
                return False
        elif r == "gluten-free":
            if "gluten-free" in tags:
                continue
            if _has_any_term(text, GLUTEN_TERMS):
                return False
        elif r not in tags:
            return False
    return True


def validate_recipe(recipe: dict) -> bool:
    title = str(recipe.get("title", "")).strip()
    ingredients = recipe.get("ingredients", [])
    instructions = recipe.get("instructions", [])
    if not title or not ingredients or not instructions:
        return False
    if len(ingredients) < 2 or len(instructions) < 1:
        return False
    placeholders = ["ingredients not available", "no ingredients listed", "instructions not available"]
    blob = _recipe_text(recipe)
    if any(p in blob for p in placeholders):
        return False
    return True


def search_and_rank(
    recipes: list[dict],
    query: Optional[str],
    restrictions: Optional[list[str]] = None,
    limit: int = 20,
) -> list[dict]:
    """Filter by dietary rules, match ingredients, rank by relevance."""
    terms = parse_ingredient_terms(query or "")

    candidates = [
        r for r in recipes
        if validate_recipe(r) and matches_dietary_restrictions(r, restrictions)
    ]

    if not terms:
        return candidates[:limit]

    scored: list[tuple[int, int, dict]] = []
    for recipe in candidates:
        if not recipe_matches_ingredients(recipe, terms):
            continue
        score = ingredient_match_score(recipe, terms)
        title_bonus = 2 if any(_term_matches(recipe.get("title", "").lower(), t) for t in terms) else 0
        scored.append((score + title_bonus, score, recipe))

    scored.sort(key=lambda x: (-x[0], -x[1], x[2].get("title", "")))
    return [recipe for _, _, recipe in scored[:limit]]
