from fastapi import APIRouter, Query
from typing import List, Optional

from services import ai_service, memory_service
from .schemas import GenerateRecipeResponse, RecipeResponse
from services import recipe_service

router = APIRouter()

@router.get("/", response_model=List[RecipeResponse])
async def get_recipes(
    ingredients: Optional[str] = Query(None),
    restrictions: Optional[List[str]] = Query(None),
    restriction: Optional[str] = Query(None)
):
    """
    Browse mode: return up to 20 existing corpus recipes ranked by vector similarity
    when embeddings are available (falls back to keyword ranking otherwise).
    Does not call the LLM composer.
    """
    effective_restrictions = list(restrictions or [])
    if restriction:
        effective_restrictions.append(restriction)
    if not effective_restrictions:
        effective_restrictions = None
    return recipe_service.get_personalized_recipes(ingredients, effective_restrictions)

@router.get("/chat")
async def chat_with_ai(
    ingredients: str,
    restrictions: Optional[List[str]] = Query(None),
    restriction: Optional[str] = Query(None)
):
    """AI Chat: Finds a recipe and adjusts it for dietary needs."""
    effective_restrictions = list(restrictions or [])
    if restriction:
        effective_restrictions.append(restriction)
    if not effective_restrictions:
        effective_restrictions = None
    return recipe_service.get_personalized_recommendation(ingredients, effective_restrictions)

@router.post("/generate-detail")
def get_ai_details(recipe: dict):
    try:
        enhanced_html = ai_service.format_recipe_nicely(recipe)
        return {"formatted_recipe": enhanced_html}
    except Exception as e:
        print(f"DEBUG: generate-detail failed: {e}")
        return {"formatted_recipe": ai_service._fallback_recipe_nicely(recipe)}

@router.post("/refine")
def refine_recipe(recipe: dict):
    try:
        refined_text = ai_service.format_recipe_nicely(recipe)
        return {"formatted_recipe": refined_text}
    except Exception as e:
        print(f"DEBUG: refine failed: {e}")
        return {"formatted_recipe": ai_service._fallback_recipe_nicely(recipe)}


@router.post("/generate", response_model=GenerateRecipeResponse)
def generate_recipe(user_input: dict):
    """
    Compose mode: retrieve top-K vector matches, then LLM writes one tailored recipe.
    Returns inspired_by titles and a bot_message for the dashboard.
    """
    restrictions = None
    try:
        user_query = user_input.get("query", "").strip()
        if not user_query:
            return GenerateRecipeResponse(
                error="Please provide a query",
                recipes=[],
                is_generated=True,
            )

        restrictions = user_input.get("restrictions")
        if isinstance(restrictions, str):
            restrictions = [restrictions]
        restriction = user_input.get("restriction") if isinstance(user_input, dict) else None
        if restriction:
            restrictions = [*(restrictions or []), restriction]

        if restrictions and not isinstance(restrictions, list):
            restrictions = [restrictions]

        cuisine = (user_input.get("cuisine") or "").strip() or None

        payload = recipe_service.compose_recipe_from_query(
            user_query, restrictions, cuisine=cuisine
        )
        recipe = payload.get("recipe") or {}
        inspired_by = payload.get("inspired_by") or []
        retrieval_note = payload.get("retrieval_note")
        rag_count = int(payload.get("rag_sample_count") or 0)
        bot_message = payload.get("bot_message")
        if not bot_message:
            if inspired_by:
                bot_message = (
                    f"I found {rag_count} similar recipes in our database and composed "
                    f"a tailored recipe inspired by them."
                )
            else:
                bot_message = "I composed a best-effort recipe from your pantry request."

        return GenerateRecipeResponse(
            recipes=[recipe],
            is_generated=True,
            inspired_by=inspired_by,
            retrieval_note=retrieval_note,
            bot_message=bot_message,
            rag_sample_count=rag_count,
        )
    except Exception as e:
        print(f"DEBUG: generate failed: {e}")
        cuisine = (user_input.get("cuisine") or "").strip() or None
        fallback = ai_service._fallback_generated_recipe(
            user_input.get("query", "chicken"),
            restrictions if isinstance(restrictions, list) else None,
            cuisine,
        )
        return GenerateRecipeResponse(
            recipes=[fallback],
            is_generated=True,
            error=str(e),
            bot_message="Generation used a fallback recipe due to an error.",
        )

@router.post("/memory/save")
def save_memory_recipe(payload: dict):
    recipe = payload.get("recipe") if isinstance(payload, dict) else None
    if not recipe:
        return {"success": False, "error": "Please provide a recipe object to save."}

    try:
        saved = ai_service.remember_recipe(
            recipe,
            user_query=payload.get("query", ""),
            notes=payload.get("notes", "")
        )
        return {"success": True, "saved_recipe": saved}
    except Exception as e:
        print(f"DEBUG: memory save failed: {e}")
        return {"success": False, "error": str(e)}

@router.get("/memory")
def list_saved_memory():
    try:
        return memory_service.get_memory_recipes()
    except Exception as e:
        print(f"DEBUG: memory list failed: {e}")
        return []

@router.get("/memory/export")
def export_training_data(limit: int = 100):
    try:
        filepath = memory_service.export_training_dataset(limit)
        return {"success": True, "training_data_path": filepath}
    except Exception as e:
        print(f"DEBUG: export training data failed: {e}")
        return {"success": False, "error": str(e)}
