from rag import retriever
from . import ai_service
from . import memory_service
import pandas as pd
import os
import re
import csv
import json
from pathlib import Path
from typing import Optional, Any

# Get the absolute path to the datasets directory
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASETS_DIR = os.path.join(BACKEND_DIR, "datasets")

# Canonical column mappings for heuristic dataset cleanup
CANONICAL_COLUMN_SYNONYMS = {
    "title": ["title", "name", "recipe_name", "recipe title", "recipe"],
    "description": ["description", "summary", "notes", "blurb", "overview", "about"],
    "ingredients": ["ingredients", "ingredient_list", "recipe_ingredients", "components", "items", "materials"],
    "instructions": ["instructions", "directions", "steps", "method", "preparation", "procedure", "step_description", "instructions_text"],
    "prep_time": ["prep_time", "prep time", "prep_time_minutes", "prep time minutes", "preparation_time", "preptime", "prep_minutes", "time_to_prep", "preparation minutes"],
    "difficulty": ["difficulty", "skill_level", "level", "complexity", "hardness"],
    "recipe_id": ["recipe_id", "id", "rid", "recipe id"],
    "recipe_name": ["recipe_name", "name", "title", "recipe title"],
    "cuisine": ["cuisine", "region", "food_type", "country"],
    "category": ["category", "course", "meal_type", "type"],
    "cooking_method": ["cooking_method", "method", "cook_method", "cooking style"],
    "servings": ["servings", "serves", "yield"],
    "spice_level": ["spice_level", "spiciness", "heat_level"],
    "meal_type": ["meal_type", "meal", "course"],
    "is_vegetarian": ["is_vegetarian", "vegetarian", "veg"],
    "is_vegan": ["is_vegan", "vegan"],
    "is_gluten_free": ["is_gluten_free", "gluten_free", "gluten free"],
    "is_halal": ["is_halal", "halal"],
    "ingredient_name": ["ingredient_name", "ingredient", "name", "item"],
    "quantity": ["quantity", "qty", "amount", "measurement"],
    "step_number": ["step_number", "step_no", "order", "sequence", "seq"],
    "step_description": ["step_description", "description", "text", "instruction", "step"]
}

# Cache for recipes (loaded once at startup)
_RECIPES_CACHE = None


def invalidate_recipe_cache():
    global _RECIPES_CACHE
    _RECIPES_CACHE = None


def preload_recipes():
    """Load and clean recipe datasets once at backend startup."""
    _load_all_recipes()


def _find_best_column_name(columns, synonyms):
    lower_map = {col.lower(): col for col in columns}
    for synonym in synonyms:
        if synonym in lower_map:
            return lower_map[synonym]

    for col_lower, original in lower_map.items():
        for synonym in synonyms:
            if synonym in col_lower or col_lower in synonym:
                return original
    return None


def _map_columns(columns):
    mapped = {}
    for canonical, synonyms in CANONICAL_COLUMN_SYNONYMS.items():
        mapped[canonical] = _find_best_column_name(columns, synonyms)
    return mapped


def _normalize_text(value):
    if value is None:
        return ""
    text = str(value).strip()
    text = re.sub(r"[\r\n]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _normalize_id(value: Any) -> str:
    """Ensure IDs match regardless of whether they are read as 1, '1', or 1.0."""
    if pd.isna(value) or value is None:
        return ""
    s = str(value).strip()
    if s.endswith('.0'):
        s = s[:-2]
    return s


def _normalize_output_recipe(recipe: dict) -> dict:
    normalized = dict(recipe)
    try:
        normalized['instructions'] = ai_service._enforce_monolithic_instructions(normalized)
    except Exception as e:
        print(f"DEBUG: Failed to normalize recipe instructions: {e}")
        if not isinstance(normalized.get('instructions'), list):
            normalized['instructions'] = ai_service._split_instruction_steps(str(normalized.get('instructions', '')))
    return normalized


def _split_bracket_aware(text: str, delimiter: str = ",") -> list[str]:
    items = []
    buffer = []
    level = 0
    in_quote = False
    quote_char = None

    for ch in text:
        if in_quote:
            buffer.append(ch)
            if ch == quote_char:
                in_quote = False
            continue

        if ch in {'"', "'"}:
            in_quote = True
            quote_char = ch
            buffer.append(ch)
            continue

        if ch == '[':
            level += 1
            buffer.append(ch)
            continue
        if ch == ']':
            level = max(0, level - 1)
            buffer.append(ch)
            continue

        if ch == delimiter and level == 0:
            items.append(''.join(buffer).strip())
            buffer = []
            continue

        buffer.append(ch)

    if buffer:
        items.append(''.join(buffer).strip())
    return [item for item in items if item]


def _try_parse_json_value(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value

    text = str(value).strip()
    if not text:
        return None

    try:
        return json.loads(text)
    except Exception:
        return text


def _normalize_cell_value(value):
    parsed = _try_parse_json_value(value)
    if isinstance(parsed, (dict, list)):
        try:
            return json.dumps(parsed, ensure_ascii=False)
        except Exception:
            return str(parsed)
    return str(parsed).strip()


def _parse_ingredients_list(ingredients_str: str) -> list[str]:
    parsed = _try_parse_json_value(ingredients_str)
    if isinstance(parsed, list):
        items = []
        for item in parsed:
            if isinstance(item, (list, dict)):
                items.append(json.dumps(item, ensure_ascii=False))
            else:
                items.append(str(item).strip())
        return [re.sub(r"^\s*\d+[\).]?\s*", "", item).strip() for item in items if item.strip()]
    if isinstance(parsed, dict):
        return [json.dumps(parsed, ensure_ascii=False)]

    raw = str(ingredients_str).strip()
    if not raw:
        return []

    if raw.startswith('[') and raw.endswith(']'):
        inner = raw[1:-1]
        parts = _split_bracket_aware(inner, delimiter=',')
        return [re.sub(r"^\s*\d+[\).]?\s*", "", item).strip().strip('"').strip("'") for item in parts if item.strip()]

    parts = []
    for segment in re.split(r"[\r\n]+", raw):
        if segment.strip():
            parts.extend(_split_bracket_aware(segment, delimiter=','))

    final = []
    for part in parts:
        cleaned = re.sub(r"^\s*\d+[\).]?\s*", "", part).strip()
        if cleaned:
            final.append(cleaned.strip('"').strip("'"))
    return final


def _load_tabular_file(file_path: str) -> pd.DataFrame:
    ext = os.path.splitext(file_path)[1].lower()
    if ext in {'.xls', '.xlsx', '.xlsm', '.xlsb'}:
        try:
            df = pd.read_excel(file_path, dtype=str)
            return df.fillna("")
        except Exception as e:
            print(f"DEBUG: Error reading Excel file {file_path}: {e}")
            return pd.DataFrame()

    if ext == '.csv':
        try:
            df = pd.read_csv(file_path, dtype=str, engine='python', sep=None)
            return df.fillna("")
        except Exception:
            raw = Path(file_path).read_text(encoding='utf-8', errors='replace').splitlines()
            if not raw:
                return pd.DataFrame()
            header_line = raw[0]
            delimiter = ';' if ';' in header_line and ',' not in header_line else ','
            rows = [_split_bracket_aware(line, delimiter=delimiter) for line in raw if line.strip()]
            header = rows[0]
            body = []
            for row in rows[1:]:
                if len(row) < len(header):
                    row = row + [''] * (len(header) - len(row))
                elif len(row) > len(header):
                    row = row[:len(header)]
                body.append(row)
            return pd.DataFrame(body, columns=header).fillna("")

    return pd.DataFrame()


def _split_list_field(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [re.sub(r"^\s*\d+[\).]?\s*", "", str(item).strip()).strip('"').strip("'") for item in value if str(item).strip()]

    return _parse_ingredients_list(value)


def _normalize_boolean_field(value):
    normalized = str(value).strip().lower()
    if not normalized:
        return False
    return normalized in {"1", "true", "yes", "y", "x", "t", "vegan", "vegetarian", "halal", "gluten-free", "gluten free", "gluten_free", "gf"}


def _collect_dietary_tags(row: Any, column_map: dict, title: str = "", description: str = "", ingredients: Optional[list[str]] = None) -> list[str]:
    tags = []
    explicit_tags = {
        "is_vegetarian": "vegetarian",
        "is_vegan": "vegan",
        "is_halal": "halal",
        "is_gluten_free": "gluten-free",
    }

    for field_name, tag_name in explicit_tags.items():
        mapped_column = column_map.get(field_name)
        if mapped_column:
            if _normalize_boolean_field(row.get(mapped_column, "")):
                tags.append(tag_name)

    text_source = " ".join([title, description, " ".join(ingredients or [])]).lower()
    if "vegan" in text_source and "vegan" not in tags:
        tags.append("vegan")
    if "vegetarian" in text_source and "vegetarian" not in tags:
        tags.append("vegetarian")
    if "halal" in text_source and "halal" not in tags:
        tags.append("halal")
    if "gluten-free" in text_source or "gluten free" in text_source or "gluten_free" in text_source:
        if "gluten-free" not in tags:
            tags.append("gluten-free")

    # If a recipe is marked vegan, it should also be vegetarian by definition
    if "vegan" in tags and "vegetarian" not in tags:
        tags.append("vegetarian")

    return tags


def _load_all_recipes() -> list:
    """
    Load recipes from all CSV datasets under the datasets directory.
    Builds recipes from known recipe tables and also includes generic CSV recipes.
    """
    global _RECIPES_CACHE
    
    if _RECIPES_CACHE is not None:
        return _RECIPES_CACHE
    
    all_recipes = []
    recipes_by_id = {}
    ingredients_by_id = {}
    steps_by_id = {}
    seen_titles = set()

    # Load recipe metadata from recipes_master.csv if present
    master_path = os.path.join(DATASETS_DIR, "recipes_master.csv")
    if os.path.exists(master_path):
        try:
            df_master = _load_tabular_file(master_path)
            print(f"DEBUG: Loaded {len(df_master)} rows from recipes_master.csv")
            master_columns = _map_columns(df_master.columns)
            for _, row in df_master.iterrows():
                recipe_id_key = master_columns.get('recipe_id') or 'recipe_id'
                recipe_id = _normalize_id(row.get(recipe_id_key))
                title_key = master_columns.get('recipe_name') or 'recipe_name'
                title = str(row.get(title_key, '')).strip() or recipe_id or "Unknown Recipe"
                cuisine = str(row.get(master_columns.get('cuisine', 'cuisine'), '')).strip()
                category = str(row.get(master_columns.get('category', 'category'), '')).strip()
                cooking_method = str(row.get(master_columns.get('cooking_method', 'cooking_method'), '')).strip()
                difficulty = str(row.get(master_columns.get('difficulty', 'difficulty'), 'Medium')).strip() or "Medium"
                
                prep_mins_key = master_columns.get('prep_time_minutes') or 'prep_time_minutes'
                prep_mins = row.get(prep_mins_key, '')
                prep_time = "30 mins"
                if pd.notna(prep_mins) and str(prep_mins).strip():
                    try: prep_time = f"{int(float(prep_mins))} mins"
                    except: pass

                description_parts = [part for part in [cuisine, category, cooking_method] if part]
                recipes_by_id[recipe_id] = {
                    'title': title,
                    'description': ", ".join(description_parts) if description_parts else "Recipe from master dataset",
                    'ingredients': [],
                    'instructions': [],
                    'prep_time': prep_time,
                    'difficulty': difficulty,
                    'dietary_tags': _collect_dietary_tags(row, master_columns, title=title, description=", ".join(description_parts)),
                    'metadata': {
                        'recipe_id': recipe_id,
                        'cuisine': cuisine,
                        'category': category,
                        'cooking_method': cooking_method,
                        'servings': row.get(master_columns.get('servings', 'servings'), ''),
                        'spice_level': row.get(master_columns.get('spice_level', 'spice_level'), ''),
                        'meal_type': row.get(master_columns.get('meal_type', 'meal_type'), ''),
                        'is_vegetarian': row.get(master_columns.get('is_vegetarian', 'is_vegetarian'), ''),
                        'is_vegan': row.get(master_columns.get('is_vegan', 'is_vegan'), ''),
                        'is_gluten_free': row.get(master_columns.get('is_gluten_free', 'is_gluten_free'), ''),
                        'is_halal': row.get(master_columns.get('is_halal', 'is_halal'), ''),
                    }
                }
        except Exception as e:
            print(f"DEBUG: Error loading recipes_master.csv: {e}")

    # Load recipe ingredients from recipe_ingredients.csv
    ingredients_path = os.path.join(DATASETS_DIR, "recipe_ingredients.csv")
    if os.path.exists(ingredients_path):
        try:
            df_ing = _load_tabular_file(ingredients_path)
            print(f"DEBUG: Loaded {len(df_ing)} rows from recipe_ingredients.csv")
            ingredient_columns = _map_columns(df_ing.columns)
            for _, row in df_ing.iterrows():
                recipe_id = _normalize_id(row.get(ingredient_columns.get('recipe_id', 'recipe_id')))
                ingredient_name = str(row.get(ingredient_columns.get('ingredient_name', 'ingredient_name'), '')).strip()
                quantity = str(row.get(ingredient_columns.get('quantity', 'quantity'), '')).strip()
                if ingredient_name:
                    line = f"{quantity} {ingredient_name}".strip()
                    ingredients_by_id.setdefault(recipe_id, []).append(line)
        except Exception as e:
            print(f"DEBUG: Error loading recipe_ingredients.csv: {e}")

    # Load recipe instructions from recipe_steps.csv
    steps_path = os.path.join(DATASETS_DIR, "recipe_steps.csv")
    if os.path.exists(steps_path):
        try:
            df_steps = _load_tabular_file(steps_path)
            print(f"DEBUG: Loaded {len(df_steps)} rows from recipe_steps.csv")
            step_columns = _map_columns(df_steps.columns)
            for _, row in df_steps.iterrows():
                recipe_id = _normalize_id(row.get(step_columns.get('recipe_id', 'recipe_id')))
                step_number = row.get(step_columns.get('step_number', 'step_number'), '')
                description = str(row.get(step_columns.get('step_description', 'step_description'), '')).strip()
                if description:
                    order = int(step_number) if pd.notna(step_number) and str(step_number).isdigit() else 999
                    steps_by_id.setdefault(recipe_id, []).append((order, description))
            for recipe_id, steps in steps_by_id.items():
                steps_by_id[recipe_id] = [desc for _, desc in sorted(steps, key=lambda item: item[0])]
        except Exception as e:
            print(f"DEBUG: Error loading recipe_steps.csv: {e}")

    # Build recipes from master dataset and attach ingredients/steps
    for recipe_id, base in recipes_by_id.items():
        recipe = {
            'title': base['title'],
            'description': base['description'],
            'ingredients': ingredients_by_id.get(recipe_id, ["Ingredients not available"]),
            'instructions': steps_by_id.get(recipe_id, ["Instructions not available"]),
            'prep_time': base['prep_time'],
            'difficulty': base['difficulty'],
            'dietary_tags': base.get('dietary_tags', []),
            'metadata': base['metadata'],
        }
        all_recipes.append(recipe)
        seen_titles.add(recipe['title'].lower())

    # Load any generic recipe CSVs that contain title/ingredients/instructions
    for filename in os.listdir(DATASETS_DIR):
        if not filename.lower().endswith(('.csv', '.xls', '.xlsx', '.xlsm', '.xlsb')):
            continue
        if filename in {"recipes_master.csv", "recipe_ingredients.csv", "recipe_steps.csv", "cuisine_metadata.csv"}:
            continue

        file_path = os.path.join(DATASETS_DIR, filename)
        try:
            df = _load_tabular_file(file_path)
            lower_columns = {col.lower() for col in df.columns}
            column_map = _map_columns(df.columns)
            if column_map['title'] and column_map['ingredients'] and column_map['instructions']:
                print(f"DEBUG: Loading generic recipes from: {filename}")
                for _, row in df.iterrows():
                    title = _normalize_text(_normalize_cell_value(row.get(column_map['title'], ""))) or f"Recipe from {filename}"
                    if title.lower() in seen_titles:
                        continue
                    description = _normalize_text(_normalize_cell_value(row.get(column_map['description'], "")))
                    ingredients = _split_list_field(row.get(column_map['ingredients']))
                    instructions = _split_list_field(row.get(column_map['instructions']))
                    prep_time = _normalize_text(_normalize_cell_value(row.get(column_map['prep_time'], "30 mins"))) or "30 mins"
                    difficulty = _normalize_text(_normalize_cell_value(row.get(column_map['difficulty'], "Medium"))) or "Medium"
                    recipe = {
                        'title': title,
                        'description': description,
                        'ingredients': ingredients if ingredients else ["No ingredients listed"],
                        'instructions': instructions if instructions else ["No instructions available"],
                        'prep_time': prep_time,
                        'difficulty': difficulty,
                        'dietary_tags': _collect_dietary_tags(row, column_map, title=title, description=description, ingredients=ingredients),
                    }
                    all_recipes.append(recipe)
                    seen_titles.add(title.lower())
        except Exception as e:
            print(f"DEBUG: Error loading generic dataset {filename}: {e}")

    # Load persisted user-generated memory recipes so the system remembers new dishes
    try:
        memory_recipes = memory_service.get_memory_recipes()
        for recipe in memory_recipes:
            title = recipe.get('title', '').strip()
            if title and title.lower() not in seen_titles:
                all_recipes.append(recipe)
                seen_titles.add(title.lower())
        if memory_recipes:
            print(f"DEBUG: Loaded {len(memory_recipes)} memorized recipes")
    except Exception as e:
        print(f"DEBUG: Failed to load memory recipes: {e}")

    print(f"DEBUG: Total recipes loaded from datasets: {len(all_recipes)}")
    _RECIPES_CACHE = all_recipes
    return all_recipes

def _validate_recipe_integrity(recipe: dict) -> bool:
    """
    Validate that a recipe has the minimum required data and isn't just placeholder text.
    """
    title = str(recipe.get('title', '')).strip()
    ingredients = recipe.get('ingredients', [])
    instructions = recipe.get('instructions', [])

    if not title or title.lower() == "unknown recipe":
        return False
    if not ingredients or not instructions:
        return False
    
    # Filter out common dataset placeholders that shouldn't be shown to users
    placeholders = ["ingredients not available", "no ingredients listed", "instructions not available", "no instructions available"]
    ing_text = " ".join(str(i) for i in ingredients).lower()
    ins_text = " ".join(str(i) for i in instructions).lower()
    
    if any(p in ing_text for p in placeholders) or any(p in ins_text for p in placeholders):
        return False
    
    # Basic sanity check: must have multiple ingredients and at least one step
    return len(ingredients) >= 2 and len(instructions) >= 1


def _normalize_restriction(restriction: str | None) -> str | None:
    if not restriction:
        return None
    value = str(restriction).strip().lower()
    if value in {"vegetarian", "vegan", "halal", "gluten-free", "gluten free", "gluten_free"}:
        if value == "gluten free":
            return "gluten-free"
        if value == "gluten_free":
            return "gluten-free"
        return value
    return None


def _matches_dietary_restriction(recipe: dict, restriction: str | None) -> bool:
    if not restriction:
        return True
    tags = [tag.lower() for tag in recipe.get('dietary_tags', []) if isinstance(tag, str)]
    if restriction == "vegetarian":
        return "vegetarian" in tags or "vegan" in tags
    return restriction in tags


def _filter_recipes_by_query_terms(recipes: list[dict], query: str) -> list[dict]:
    if not query:
        return recipes
    return [recipe for recipe in recipes if ai_service._recipe_contains_query_terms(recipe, query)]


def get_personalized_recipes(query: Optional[str] = None, restriction: Optional[str] = None):
    """
    Used for the standard search bar.
    Finds recipes using both keyword matching and semantic search (RAG).
    Returns best matches ranked by relevance.
    """
    all_recipes = _load_all_recipes()

    restriction_normalized = _normalize_restriction(restriction)
    if not query:
        # Return only validated recipes for default view
        validated_recipes = [r for r in all_recipes if _validate_recipe_integrity(r) and _matches_dietary_restriction(r, restriction_normalized)]
        return [_normalize_output_recipe(recipe) for recipe in validated_recipes[:20]]

    # 1. Keyword-based search (fast, exact matches)
    query_lower = query.lower()
    keyword_results = []
    for recipe in all_recipes:
        # Only include validated recipes
        if not _validate_recipe_integrity(recipe):
            continue

        title_match = query_lower in recipe['title'].lower()
        description_match = query_lower in recipe['description'].lower()
        ingredients_text = " ".join(recipe.get('ingredients', [])).lower()
        instructions_text = " ".join(recipe.get('instructions', [])).lower()
        ingredient_match = query_lower in ingredients_text
        instruction_match = query_lower in instructions_text
        if title_match or description_match or ingredient_match or instruction_match:
            if _matches_dietary_restriction(recipe, restriction_normalized):
                keyword_results.append(recipe)

    # If keyword search found results, filter by strong query terms when present
    if keyword_results:
        keyword_results = _filter_recipes_by_query_terms(keyword_results, query)
        if keyword_results:
            print(f"DEBUG: Keyword search found {len(keyword_results)} validated recipes after query-term enforcement")
            return [_normalize_output_recipe(recipe) for recipe in keyword_results]
        print(f"DEBUG: Keyword search had matches but none contained query ingredient terms for query={query}")

    # 2. Semantic search (RAG) - if keyword search didn't find anything or query-term filtering removed them
    print(f"DEBUG: No keyword matches, using semantic search for query: {query}")
    try:
        semantic_results = retriever.find_best_recipes(query, top_k=10)
        # Filter semantic results for validity, dietary restrictions, and query terms
        validated_semantic = [r for r in semantic_results if _validate_recipe_integrity(r) and _matches_dietary_restriction(r, restriction_normalized)]
        validated_semantic = _filter_recipes_by_query_terms(validated_semantic, query)
        if validated_semantic:
            print(f"DEBUG: Semantic search found {len(validated_semantic)} validated recipes after query-term enforcement")
            return [_normalize_output_recipe(recipe) for recipe in validated_semantic]
        print(f"DEBUG: Semantic matches found but none contained query ingredient terms for query={query}")
    except Exception as e:
        print(f"DEBUG: Semantic search failed: {e}")

    # Fallback: return validated recipes if no matches at all
    validated_recipes = [r for r in all_recipes if _validate_recipe_integrity(r)]
    return [_normalize_output_recipe(recipe) for recipe in validated_recipes[:10]]

def get_personalized_recommendation(query: str, restriction: Optional[str] = None):
    """
    Used for the AI Chatbot.
    Finds a recipe AND applies AI dietary adjustments.
    """
    matches = retriever.find_best_recipes(query)
    
    if not matches:
        return {"ai_chat_response": "I couldn't find a specific recipe for that. Would you like me to try generating a new one?", "recipe_details": None}

    top_recipe = matches[0]
    for candidate in matches:
        if ai_service._recipe_contains_query_terms(candidate, query):
            top_recipe = candidate
            break

    if top_recipe is not matches[0]:
        print(f"DEBUG: selected alternate semantic match containing query terms for query={query}")

    ai_comment = ai_service.adjust_recipe_for_restrictions(top_recipe, restriction)
    
    return {
        "ai_chat_response": ai_comment,
        "recipe_details": _normalize_output_recipe(top_recipe)
    }