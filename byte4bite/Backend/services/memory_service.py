import json
import os
import uuid
from datetime import datetime

# Get the absolute path to the backend directory
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_FILE = os.path.join(BACKEND_DIR, "memory_store.json")
FINE_TUNING_FILE = os.path.join(BACKEND_DIR, "fine_tuning_data.jsonl")


def _ensure_memory_file() -> None:
    if not os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "w", encoding="utf-8") as file:
            json.dump({"recipes": []}, file, indent=2)


def _load_memory_store() -> dict:
    _ensure_memory_file()
    with open(MEMORY_FILE, "r", encoding="utf-8") as file:
        try:
            return json.load(file)
        except json.JSONDecodeError:
            return {"recipes": []}


def _save_memory_store(data: dict) -> None:
    with open(MEMORY_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def get_memory_recipes() -> list:
    return _load_memory_store().get("recipes", [])


def get_trained_recipe_examples(limit: int = 2) -> list:
    recipes = get_memory_recipes()
    return recipes[-limit:]


def clear_all_recipe_memory() -> dict[str, int]:
    """
    Wipe every persisted 'memory' of old recipes:
      - memory_store.json (AI learning examples)
      - fine_tuning_data.jsonl (exported training snapshots)
      - saved_recipes bookmarks in MySQL
      - asian_recipes rows with source_file = 'user_saved'
    Does not delete the main dataset corpus (CSV/Excel ingested recipes).
    """
    _save_memory_store({"recipes": []})
    json_cleared = 1

    fine_tuning_removed = 0
    if os.path.exists(FINE_TUNING_FILE):
        os.remove(FINE_TUNING_FILE)
        fine_tuning_removed = 1

    from database.recipe_repository import RecipeRepository

    bookmarks = RecipeRepository.clear_all_saved_recipes()
    user_saved = RecipeRepository.delete_user_saved_corpus()

    try:
        from . import recipe_service

        recipe_service.invalidate_recipe_cache()
    except Exception:
        pass

    try:
        from ..rag import retriever as rag_retriever

        rag_retriever.invalidate_embedding_cache()
    except Exception:
        pass

    return {
        "memory_json_cleared": json_cleared,
        "fine_tuning_removed": fine_tuning_removed,
        "saved_recipes_deleted": bookmarks,
        "user_saved_deleted": user_saved,
    }


def export_training_dataset(limit: int = 100) -> str:
    from .recipe_service import _load_all_recipes

    recipes = _load_all_recipes()
    if not recipes:
        raise RuntimeError("No recipes are available to export training data.")

    examples = []
    for recipe in recipes[:limit]:
        input_text = (
            f"Create a unique recipe using these ingredients: {', '.join(recipe.get('ingredients', []))}. "
            f"The dish should be original, flavorful, and suitable for home cooking."
        )
        output_text = (
            f"TITLE: {recipe.get('title', 'Recipe')}\n"
            f"DESCRIPTION: {recipe.get('description', 'A tasty homemade dish.')}\n"
            f"INGREDIENTS: {', '.join(recipe.get('ingredients', []))}\n"
            f"INSTRUCTIONS: {' '.join(recipe.get('instructions', []))}\n"
            f"PREP_TIME: {recipe.get('prep_time', '30 mins')}\n"
            f"DIFFICULTY: {recipe.get('difficulty', 'Medium')}"
        )
        examples.append({"input_text": input_text, "output_text": output_text})

    with open(FINE_TUNING_FILE, "w", encoding="utf-8") as file:
        for example in examples:
            file.write(json.dumps(example, ensure_ascii=False) + "\n")

    return FINE_TUNING_FILE


from typing import Optional


def save_recipe_memory(recipe: dict, source: str = "generated", user_notes: Optional[str] = None, user_query: Optional[str] = None) -> dict:
    data = _load_memory_store()
    memory_recipes = data.setdefault("recipes", [])

    recipe_id = str(uuid.uuid4())
    saved_recipe = {
        "id": recipe_id,
        "title": recipe.get("title", "Saved Recipe"),
        "description": recipe.get("description", "A learned recipe."),
        "ingredients": recipe.get("ingredients", []),
        "instructions": recipe.get("instructions", []),
        "prep_time": recipe.get("prep_time", "30 mins"),
        "difficulty": recipe.get("difficulty", "Medium"),
        "dietary_tags": recipe.get("dietary_tags", []),
        "source": source,
        "user_notes": user_notes or "",
        "user_query": user_query or "",
        "is_generated": recipe.get("is_generated", True),
        "created_at": datetime.utcnow().isoformat() + "Z",
    }

    memory_recipes.append(saved_recipe)
    _save_memory_store(data)

    try:
        from ..rag import retriever as rag_retriever

        rag_retriever.invalidate_embedding_cache()
    except Exception:
        pass

    try:
        from . import recipe_service

        recipe_service.invalidate_recipe_cache()
    except Exception:
        pass

    return saved_recipe
