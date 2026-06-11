"""
Dataset parsing utilities shared by ingest.py and search fallbacks.

Supports CSV and Excel (.xlsx) files in Backend/datasets/.
All raw ingredient/instruction cells pass through text_consolidation before
being stored or returned to the API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pandas as pd

from services.text_consolidation import (
    consolidate_raw_text_stream,
    normalize_ingredient_list,
    normalize_instruction_list,
    parse_python_style_list,
    sanitize_recipe_instructions,
    SEPARATOR,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATASETS_DIR = BACKEND_DIR / "datasets"

CANONICAL_COLUMN_SYNONYMS = {
    "title": ["title", "name", "recipe_name", "recipe title", "recipe"],
    "description": ["description", "summary", "notes", "blurb", "overview", "about"],
    "ingredients": [
        "ingredients", "ingredient_list", "recipe_ingredients",
        "components", "items", "materials", "cleaned_ingredients",
    ],
    "instructions": [
        "instructions", "directions", "steps", "method", "preparation",
        "procedure", "step_description", "instructions_text",
    ],
    "prep_time": [
        "prep_time", "prep time", "prep_time_minutes", "preparation_time", "preptime",
    ],
    "difficulty": ["difficulty", "skill_level", "level", "complexity"],
    "cuisine": ["cuisine", "region", "food_type", "country"],
}


def _find_column(columns: list[str], synonyms: list[str]) -> Optional[str]:
    lower_map = {col.lower(): col for col in columns}
    for synonym in synonyms:
        if synonym in lower_map:
            return lower_map[synonym]
    for col_lower, original in lower_map.items():
        for synonym in synonyms:
            if synonym in col_lower or col_lower in synonym:
                return original
    return None


def _map_columns(columns: list[str]) -> dict[str, Optional[str]]:
    return {
        key: _find_column(columns, synonyms)
        for key, synonyms in CANONICAL_COLUMN_SYNONYMS.items()
    }


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    import re
    text = consolidate_raw_text_stream(str(value))
    return re.sub(r"\s+", " ", text.replace(SEPARATOR, " ")).strip()


def list_dataset_files() -> list[Path]:
    """All supported recipe dataset files in datasets/."""
    files = sorted(DATASETS_DIR.glob("*.csv")) + sorted(DATASETS_DIR.glob("*.xlsx"))
    return files


def _load_dataset(path: Path) -> pd.DataFrame:
    try:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return pd.read_csv(path, dtype=str, engine="python", sep=None).fillna("")
        if suffix in {".xlsx", ".xls"}:
            return pd.read_excel(path, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame()


def _iter_recipes_from_dataframe(df: pd.DataFrame, path: Path) -> list[dict[str, Any]]:
    if df.empty:
        return []

    column_map = _map_columns(list(df.columns))
    if not column_map.get("title") or not column_map.get("ingredients"):
        return []

    recipes: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        title = _normalize_text(row.get(column_map["title"], ""))
        if not title:
            continue

        raw_ingredients = row.get(column_map.get("ingredients"), "")
        raw_instructions = row.get(column_map.get("instructions"), "") if column_map.get("instructions") else ""

        ingredients = parse_python_style_list(raw_ingredients)
        if ingredients is None:
            ingredients = normalize_ingredient_list(raw_ingredients)
        instructions = normalize_instruction_list(
            sanitize_recipe_instructions(raw_instructions)
        )

        if len(ingredients) < 2 or len(instructions) < 1:
            continue

        description = _normalize_text(row.get(column_map.get("description"), ""))
        prep_time = _normalize_text(row.get(column_map.get("prep_time"), "30 mins")) or "30 mins"
        difficulty = _normalize_text(row.get(column_map.get("difficulty"), "Medium")) or "Medium"
        if difficulty not in {"Easy", "Medium", "Hard"}:
            difficulty = "Medium"
        cuisine = _normalize_text(row.get(column_map.get("cuisine"), "")) or None

        recipes.append({
            "title": title,
            "description": description or f"Recipe from {path.name}",
            "ingredients": ingredients,
            "instructions": instructions,
            "prep_time": prep_time,
            "difficulty": difficulty,
            "cuisine": cuisine,
            "dietary_tags": [],
            "source_file": path.name,
        })

    return recipes


def iter_recipes_from_dataset(path: Path) -> list[dict[str, Any]]:
    """Parse one CSV or Excel dataset file into normalized recipe dicts."""
    return _iter_recipes_from_dataframe(_load_dataset(path), path)


def iter_recipes_from_csv(path: Path) -> list[dict[str, Any]]:
    """Backward-compatible alias for iter_recipes_from_dataset."""
    return iter_recipes_from_dataset(path)


def iter_all_dataset_recipes() -> list[dict[str, Any]]:
    """Load every parseable recipe from datasets/*.csv and datasets/*.xlsx."""
    all_recipes: list[dict[str, Any]] = []
    for dataset_path in list_dataset_files():
        all_recipes.extend(iter_recipes_from_dataset(dataset_path))
    return all_recipes
