try:
    from google import genai
except Exception:
    genai = None

from .memory_service import get_trained_recipe_examples, save_recipe_memory
import re
import json
from datetime import datetime
from typing import Optional, List, Any
import os

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-1.5-flash"  # Faster, cheaper Gemini (or use gemini-pro for better quality)
client = genai.Client(api_key=API_KEY) if (genai is not None and API_KEY) else None

# Zero-shot persona header to encourage consistent behavior
ZERO_SHOT_PERSONA = (
    "You are an expert culinary assistant. Respond in a single concise voice, "
    "use professional, precise, and friendly guidance, and produce only the structured "
    "schema requested with no extra commentary."
)

# Cooking time estimates (in minutes) for different ingredient types
COOKING_TIME_ESTIMATES = {
    "rice": {"prep": 5, "cook": 20},
    "noodles": {"prep": 3, "cook": 8},
    "chicken": {"prep": 10, "cook": 20},
    "beef": {"prep": 10, "cook": 25},
    "fish": {"prep": 5, "cook": 12},
    "tofu": {"prep": 5, "cook": 10},
    "vegetable": {"prep": 8, "cook": 10},
    "sauce": {"prep": 3, "cook": 5},
}


def _clean_step_text(step: str) -> str:
    step = step.strip()
    step = re.sub(r'^\s*\d+[\).]?\s*', '', step)
    step = step.strip('"“”')
    return step


def _strip_quotes(text: str) -> str:
    if text is None:
        return ''
    cleaned = str(text).strip()
    cleaned = cleaned.strip('"“”')
    cleaned = cleaned.replace('“', '').replace('”', '').replace('"', '')
    return cleaned.strip()


def _try_parse_json_value(text: str):
    if text is None:
        return None
    if isinstance(text, (dict, list)):
        return text
    value = str(text).strip()
    try:
        return json.loads(value)
    except Exception:
        return value


def _split_sentences(text: str) -> list[str]:
    if not text:
        return []
    continuation_words = r'(?:While|When|Because|Since|Although|After|Before|Unless|And|But|Then|Meanwhile|If)'
    sentences = re.split(rf'(?<=[.!?])\s+(?=(?!{continuation_words}\b)[A-Z])', text.strip())
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def _parse_ingredients_list(ingredients_str: str) -> list[str]:
    parsed = _try_parse_json_value(ingredients_str)
    if isinstance(parsed, list):
        items = []
        for item in parsed:
            if isinstance(item, (list, dict)):
                items.append(json.dumps(item, ensure_ascii=False))
            else:
                items.append(str(item).strip())
        return [_strip_quotes(item).strip() for item in items if item.strip()]
    if isinstance(parsed, dict):
        return [json.dumps(parsed, ensure_ascii=False)]

    cleaned = _strip_quotes(parsed).strip()
    if not cleaned:
        return []

    # Handle bullet- or line-separated ingredient lists first.
    lines = [re.sub(r'^\s*(?:[-*•]\s+)', '', line).strip() for line in cleaned.splitlines() if line.strip()]
    if len(lines) > 1:
        return [_strip_quotes(line) for line in lines if line]

    # Handle bracketed array strings like ["a, b", "c"]
    if cleaned.startswith('[') and cleaned.endswith(']'):
        inner = cleaned[1:-1]
        parts = re.split(r',(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)', inner)
        return [re.sub(r'^\s*\d+[\).]?\s*', '', _strip_quotes(part)).strip() for part in parts if part.strip()]

    # Handle semicolon-separated lists.
    if ';' in cleaned and ',' not in cleaned:
        parts = [part.strip() for part in cleaned.split(';') if part.strip()]
        return [_strip_quotes(part) for part in parts]

    # Default to comma-separated ingredients.
    parts = [part.strip() for part in cleaned.split(',') if part.strip()]
    return [_strip_quotes(part) for part in parts]


def _split_instruction_steps(text: str) -> list[str]:
    if not text:
        return []
    parsed = _try_parse_json_value(text)
    if isinstance(parsed, list):
        return [_strip_quotes(str(item)) for item in parsed if str(item).strip()]
    if isinstance(parsed, dict):
        return [_strip_quotes(json.dumps(parsed, ensure_ascii=False))]

    cleaned_text = _strip_quotes(text).strip()
    cleaned_text = re.sub(r'^\s*\d+[.)]\s*', '', cleaned_text)
    cleaned_text = cleaned_text.replace('\r\n', '\n').replace('\r', '\n')

    lines = [line.strip() for line in cleaned_text.split('\n') if line.strip()]
    if len(lines) > 1:
        merged_lines = []
        for line in lines:
            if merged_lines and re.match(r'^(?:Meanwhile|While|Then|And|But|After|Before|When|If)\b', line, flags=re.IGNORECASE):
                merged_lines[-1] = f"{merged_lines[-1].rstrip()} {line}"
            else:
                merged_lines.append(line)

        explicit_step_breaks = any(
            re.match(r'^(?:\d+[.)]|[-*•])', line) or re.search(r'[.!?]$', line)
            for line in merged_lines
        )
        if explicit_step_breaks and all(
            len(line) > 40 or re.match(r'^(?:\d+[.)]|[-*•])', line)
            for line in merged_lines
        ):
            return [_strip_quotes(re.sub(r'^\s*(?:\d+[.)]\s+|[-*•]\s+)', '', line)) for line in merged_lines if line]
        cleaned_text = " ".join(merged_lines)

    # Prefer numbered or line-separated steps when present.
    lines = [re.sub(r'^\s*(?:\d+[.)]\s+|[-*•]\s+)', '', line).strip() for line in cleaned_text.splitlines() if line.strip()]
    if len(lines) > 1:
        return [_strip_quotes(line) for line in lines if line]

    # Handle inline numbered steps on a single line, e.g. "1. Step one. 2. Step two."
    inline_numbered = re.split(r'(?<=\.)\s+(?=\d+[.)]\s+)', cleaned_text)
    if len(inline_numbered) > 1:
        parsed_steps = []
        for part in inline_numbered:
            step = re.sub(r'^\s*\d+[.)]\s*', '', part).strip()
            if step:
                parsed_steps.append(_strip_quotes(step))
        if parsed_steps:
            return parsed_steps

    # Fall back to sentence-aware splitting when instructions are in one line.
    steps = re.split(r'(?<=[.!?])\s+(?=[A-Z])', cleaned_text)
    return [_strip_quotes(step) for step in steps if step.strip()]


def _dedupe_ordered(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        normalized = re.sub(r'\s+', ' ', item.strip().lower())
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(item.strip())
    return result


def _normalize_recipe_fields(recipe: dict) -> tuple[list[str], list[str]]:
    ingredients = recipe.get("ingredients", [])
    instructions = recipe.get("instructions", [])

    if isinstance(ingredients, str):
        ingredients = _parse_ingredients_list(ingredients)
    if isinstance(instructions, str):
        instructions = _split_instruction_steps(instructions)

    ingredients = _dedupe_ordered(ingredients)
    instructions = [_clean_step_text(step) for step in instructions if _clean_step_text(step)]
    instructions = _dedupe_ordered(instructions)

    return ingredients, instructions


def _preprocess_query(query: str) -> str:
    if not query:
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9, ]+", " ", query).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _build_reference_prompt(query_text: str, recipe_samples: list) -> str:
    if not recipe_samples:
        return ""
    context = ["Use these recipes only as inspiration and do not copy them:"]
    for sample in recipe_samples:
        title = sample.get('title', 'Recipe')
        desc = sample.get('description', '')
        ingredients = ', '.join(sample.get('ingredients', []))
        context.append(f"- {title}: {desc}. Ingredients: {ingredients}.")
    return "\n".join(context)


def _validate_generated_recipe(recipe: dict, query_text: str) -> dict:
    if not recipe.get('title'):
        recipe['title'] = 'Chef Special Recipe'

    ingredients, instructions = _normalize_recipe_fields(recipe)
    if not ingredients:
        recipe['ingredients'] = ['2 tbsp soy sauce', '1 tbsp sesame oil', '2 cloves garlic']
    else:
        recipe['ingredients'] = ingredients

    if not instructions:
        recipe['instructions'] = ['Prepare all ingredients.', 'Cook and serve.']
    else:
        recipe['instructions'] = instructions

    # Ensure timing exists for all steps and enforce monolithic single-sentence steps
    recipe['instructions'] = _enforce_monolithic_instructions(recipe)

    if not recipe.get('prep_time') or 'min' not in recipe.get('prep_time', ''):
        total_minutes = _estimate_total_cooking_time(recipe['ingredients'])
        recipe['prep_time'] = f"{total_minutes} mins"

    if recipe.get('difficulty') not in ['Easy', 'Medium', 'Hard']:
        recipe['difficulty'] = 'Medium'

    return recipe


def _build_recipe_example() -> str:
    return (
        "Example recipe format:\n"
        "TITLE: Coconut Ginger Stir-Fry\n"
        "DESCRIPTION: A fragrant, quick Asian-inspired stir-fry with ginger and coconut notes.\n"
        "INGREDIENTS: 250g chicken, 2 tbsp soy sauce, 1 tbsp sesame oil, 1 tbsp ginger, 1 cup mixed vegetables\n"
        "INSTRUCTIONS: Heat oil in a skillet (1 min). Add ginger and garlic, sauté until fragrant (2 mins). Add chicken and cook until browned (5 mins). Stir in vegetables and soy sauce, cook until tender (4 mins). Finish with sesame oil and toss well (1 min). Serve hot.\n"
        "PREP_TIME: 15 mins\n"
        "DIFFICULTY: Easy\n"
    )


def _estimate_ingredient_quantity(ingredient: str) -> str:
    """Add quantity estimates to ingredients that don't have them."""
    lower = ingredient.lower()
    
    # Check for actual measurement units (with word boundaries or spaces)
    import re
    unit_pattern = r'\b(?:cup|tbsp|tsp|gram|g|kg|ml|l|oz|pound|can|slice|slices)\b'
    if re.search(unit_pattern, lower):
        return ingredient

    hints = {
        "rice noodles": "200g rice noodles",
        "ramen noodles": "200g ramen noodles",
        "soy sauce": "2 tbsp soy sauce",
        "miso": "2 tbsp miso paste",
        "coconut milk": "1 can coconut milk",
        "bean sprouts": "1 cup bean sprouts",
        "green curry paste": "2 tbsp green curry paste",
        "egg": "2 eggs",
        "eggs": "2 eggs",
        "chicken": "250g chicken",
        "tofu": "200g tofu",
        "broth": "2 cups broth",
        "lime": "1 lime",
        "ginger": "1 thumb-sized piece of ginger",
    }

    for key, value in hints.items():
        if key in lower:
            return value

    return ingredient


def _format_recipe_timing(raw_recipe: dict) -> str:
    parts = []
    prep_time = raw_recipe.get('prep_time')
    difficulty = raw_recipe.get('difficulty')
    if prep_time:
        parts.append(f"Prep Time: {prep_time}")
    if difficulty:
        parts.append(f"Difficulty: {difficulty}")
    if parts:
        return " | ".join(parts)
    return ""


def _fallback_recipe_nicely(raw_recipe: dict) -> str:
    ingredients, instructions = _normalize_recipe_fields(raw_recipe)
    title = raw_recipe.get('title', 'Recipe')
    description = raw_recipe.get('description', '')
    timing = _format_recipe_timing(raw_recipe)

    lines = [
        f"Chef's Note: {description or 'A tasty dish ready for your kitchen.'}",
    ]
    if timing:
        lines.append(timing)
    lines.extend(["", "What You'll Need:"])

    for item in ingredients:
        lines.append(f"• {_estimate_ingredient_quantity(item)}")

    lines.extend(["", "Easy Steps:"])
    for idx, step in enumerate(instructions, 1):
        clean_step = _strip_quotes(step)
        if not clean_step.endswith('.'):
            clean_step = f"{clean_step}."
        lines.append(f"{idx}. {clean_step}")

    lines.extend(["", "Chef's Tip: Taste as you cook and add seasoning gradually."])
    return "\n".join(lines)


def _build_memory_learning_context(user_query: str) -> str:
    memory_examples = get_trained_recipe_examples(limit=2)
    if not memory_examples:
        return ""

    context_lines = [
        "\nUse the chef's learned recipes as inspiration for a fresher result:",
    ]
    for recipe in memory_examples:
        ingredients = ", ".join(recipe.get('ingredients', []))
        context_lines.append(f"- {recipe.get('title', 'Saved Dish')}: {recipe.get('description', '')}. Ingredients: {ingredients}.")

    return "\n".join(context_lines)


def remember_recipe(recipe: dict, user_query: Optional[str] = None, notes: Optional[str] = None) -> dict:
    try:
        return save_recipe_memory(recipe, source="generated", user_notes=notes, user_query=user_query)
    except Exception as e:
        print(f"DEBUG ERROR saving recipe memory: {e}")
        return recipe


def _enhance_recipe_quality(recipe: dict, reference_recipes: Optional[list] = None) -> dict:
    """
    Enhance recipe with better instructions, timing, and clarity.
    Uses reference recipes to ensure uniqueness and accuracy.
    """
    ingredients = recipe.get('ingredients', [])
    instructions = recipe.get('instructions', [])
    
    # Estimate total time
    total_minutes = _estimate_total_cooking_time(ingredients)
    recipe['prep_time'] = f"{total_minutes} mins"
    
    # Enhance instructions with timing and clarity
    enhanced_instructions = []
    for instruction in instructions:
        instruction = re.sub(r'^\d+\.\s*', '', instruction).strip()
        instruction = instruction.rstrip('.')
        if '(' not in instruction or 'min' not in instruction:
            estimated_time = max(2, total_minutes // max(len(instructions), 1))
            instruction = f"{instruction} ({estimated_time} mins)"
        instruction = instruction[0].upper() + instruction[1:] if instruction else instruction
        if instruction and not instruction.endswith('.'):
            instruction = f"{instruction}."
        enhanced_instructions.append(instruction)

    recipe['instructions'] = _dedupe_ordered(enhanced_instructions)
    return recipe


def _generate_unique_variant(base_recipe: dict, reference_recipes: Optional[list] = None) -> dict:
    """
    Generate a unique variant by suggesting ingredient swaps and cooking method changes.
    """
    ingredients = base_recipe.get('ingredients', [])
    
    # Suggest complementary additions
    additions = {
        'garlic': ['ginger', 'scallions'],
        'soy sauce': ['rice vinegar', 'sesame oil'],
        'chicken': ['mushrooms', 'snap peas'],
        'rice': ['jasmine rice', 'sticky rice'],
    }
    
    for ingredient in ingredients:
        for key, swaps in additions.items():
            if key in ingredient.lower():
                # Could add variants here
                pass
    
    return base_recipe


def _estimate_total_cooking_time(ingredients: list) -> int:
    """Estimate total cooking time based on ingredients."""
    prep_time = 10  # Base prep
    cook_time = 15  # Base cook
    
    for ingredient in ingredients:
        ing_lower = ingredient.lower()
        for key, times in COOKING_TIME_ESTIMATES.items():
            if key in ing_lower:
                cook_time = max(cook_time, times["cook"])
                prep_time = max(prep_time, times["prep"])
    
    return prep_time + cook_time


def _has_timing(step: str) -> bool:
    return bool(re.search(r"\(\s*\d+\s*(?:min|mins|minutes)\s*\)", step))


def _make_monolithic_sentence(step: str, default_minutes: int) -> str:
    """Convert a step into a single monolithic sentence and ensure timing."""
    if not step:
        return "Prepare ingredients and proceed (2 mins)."

    s = _strip_quotes(step).strip()
    # Replace semicolons with commas to avoid multiple independent clauses
    s = s.replace(';', ',')
    # Split into sentences and join into one sentence with commas
    parts = _split_sentences(s)
    if len(parts) <= 1:
        sentence = parts[0] if parts else s
    else:
        # Join with commas but avoid duplicating end punctuation
        cleaned = [p.rstrip('.').strip() for p in parts if p.strip()]
        sentence = ', '.join(cleaned)

    # Remove internal periods other than the final one
    sentence = re.sub(r'\.(?=[^.]*\.)', ',', sentence)

    # Ensure timing present
    if not _has_timing(sentence):
        sentence = sentence.rstrip('.').strip()
        sentence = f"{sentence} ({default_minutes} mins)"

    # Ensure single ending period
    if not sentence.endswith('.'):
        sentence = f"{sentence}."

    # Remove any duplicate whitespace
    sentence = re.sub(r'\s+', ' ', sentence).strip()
    return sentence


def _enforce_monolithic_instructions(recipe: dict) -> list[str]:
    instructions = recipe.get('instructions', []) or []
    # Normalize into list of strings
    if isinstance(instructions, str):
        instructions = _split_instruction_steps(instructions)

    if isinstance(instructions, list):
        merged_instructions = []
        for step in instructions:
            step_text = str(step).strip()
            if merged_instructions and re.match(r'^(?:Meanwhile|While|Then|And|But|After|Before|When|If)\b', step_text, flags=re.IGNORECASE) and len(step_text.split()) < 10:
                merged_instructions[-1] = f"{merged_instructions[-1].rstrip()} {step_text}"
            else:
                merged_instructions.append(step_text)
        instructions = merged_instructions

    total_minutes = _estimate_total_cooking_time(recipe.get('ingredients', []))
    per_step = max(1, total_minutes // max(len(instructions), 1))

    processed = []
    for step in instructions:
        monolith = _make_monolithic_sentence(step, per_step)
        processed.append(monolith)

    # Deduplicate while preserving order
    processed = _dedupe_ordered(processed)

    # Preserve monolithic instruction sentences; do not split natural connector clauses like ", then".
    if len(processed) < 6:
        processed = _dedupe_ordered(processed)

    return processed


QUERY_INGREDIENT_SYNONYMS = {
    'beef': ['beef', 'steak', 'brisket', 'sirloin', 'ground beef', 'chuck', 'roast'],
    'chicken': ['chicken', 'poultry', 'breast', 'thigh', 'drumstick'],
    'pork': ['pork', 'bacon', 'ham', 'pork loin', 'pork belly'],
    'fish': ['fish', 'salmon', 'tuna', 'cod', 'trout', 'tilapia'],
    'shrimp': ['shrimp', 'prawn'],
    'tofu': ['tofu'],
    'lamb': ['lamb', 'mutton'],
    'turkey': ['turkey'],
    'egg': ['egg', 'eggs'],
    'mushroom': ['mushroom', 'shiitake', 'portobello', 'cremini']
}


def _extract_query_tokens(query: str) -> list[str]:
    tokens = [token.lower() for token in re.findall(r"[A-Za-z]+", query)]
    stopwords = {'and', 'with', 'or', 'in', 'the', 'a', 'an', 'of', 'for', 'to', 'on', 'by', 'from', 'as', 'from'}
    return [token for token in tokens if token not in stopwords]


def _extract_strong_query_ingredients(query: str) -> list[str]:
    query_tokens = _extract_query_tokens(query)
    strong_terms = []
    for main_term, synonyms in QUERY_INGREDIENT_SYNONYMS.items():
        if any(token in query_tokens for token in synonyms):
            strong_terms.append(main_term)
    if not strong_terms:
        # Fall back to the first query token if it looks ingredient-like
        strong_terms = [query_tokens[0]] if query_tokens else []
    return strong_terms


def _recipe_contains_query_terms(recipe: dict, query_text: str) -> bool:
    ingredients_text = ' '.join(recipe.get('ingredients', [])).lower()
    title_text = str(recipe.get('title', '')).lower()
    description_text = str(recipe.get('description', '')).lower()
    strong_terms = _extract_strong_query_ingredients(query_text)
    for term in strong_terms:
        # Search for the term or any of its synonyms in the recipe content
        synonyms = QUERY_INGREDIENT_SYNONYMS.get(term, [term])
        for syn in synonyms:
            pattern = rf"\b{re.escape(syn)}\b"
            if re.search(pattern, ingredients_text) or re.search(pattern, title_text) or re.search(pattern, description_text):
                return True
    return False


def _ensure_recipe_contains_query_terms(recipe: dict, query_text: str) -> dict:
    strong_terms = _extract_strong_query_ingredients(query_text)
    if not strong_terms:
        return recipe

    if _recipe_contains_query_terms(recipe, query_text):
        return recipe

    print(f"DEBUG: Recipe missing required query ingredient terms {strong_terms}; switching to strict fallback for query={query_text}")
    return _fallback_generated_recipe(query_text)


def adjust_recipe_for_restrictions(recipe: dict, restriction: Optional[str] = None) -> str:
    title = recipe.get('title', 'Unknown Dish')
    ingredients, instructions = _normalize_recipe_fields(recipe)
    prompt = f"""
    Format this Asian recipe for a premium cooking app: {title}.

    Raw instructions may contain broken fragments or random line breaks. Stitch any fragmented text back into complete, coherent sentences.

    Produce a structured cooking guide with:
    1. A short introduction describing the flavor and total time.
    2. A 'What You'll Need' list with quantities.
    3. Numbered, sequential cooking steps with TIMING in parentheses (e.g., "5 mins").
    4. One practical chef tip.

    Do not repeat any steps or ingredients. Do not include duplicate or vague instructions.
    Each step must be a complete sentence and specific.
    Do not break a sentence because of a comma.
    Do not create a new step for single words like "Meanwhile" or "Then"; merge them naturally into the cooking flow.
    Include estimated duration for each step based on the cooking technique.
    """

    if client is None:
        return _fallback_recipe_nicely(recipe)
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )
        return response.text or ""
    except Exception as e:
        print(f"DEBUG ERROR in adjust_recipe_for_restrictions: {e}")
        return _fallback_recipe_nicely(recipe)


def format_recipe_nicely(raw_recipe: dict) -> str:
    ingredients, instructions = _normalize_recipe_fields(raw_recipe)
    title = raw_recipe.get('title', 'Recipe')
    description = raw_recipe.get('description', '')
    timing = _format_recipe_timing(raw_recipe)

    prompt = f"""
    {ZERO_SHOT_PERSONA}
    Rewrite this recipe into a professional cooking guide.

    The source instructions may be fragmented or split across random lines. Stitch broken phrases together into complete, coherent sentences.

    Dish: {title}
    Description: {description}
    Ingredients: {ingredients}
    Instructions: {instructions}
    Prep Time: {raw_recipe.get('prep_time', 'Unknown')}

    Output requirements:
    - A 1-sentence intro describing the flavor and total preparation time.
    - A 'What You'll Need' bullet list with quantities.
    - Numbered sequential cooking steps that expand each raw step into detailed actions.
    - Each numbered step must be ONE monolithic natural-sounding sentence that synthesizes raw info into a single sentence; do not include multiple sentences, semicolons, or line breaks within a step.
    - Each step must include timing in parentheses (e.g., "5 mins").
    - Do not break a sentence because it contains a comma.
    - Do not create a new step for single words like "Meanwhile" or "Then"; merge them naturally into the cooking flow.
    - Do not repeat any step or ingredient. Avoid duplicate wording and vague phrases.
    - Do not use quotation marks anywhere in the ingredients or instructions.
    - Include a 'Total Time' line and one short chef tip.
    - If the ingredient list is short, infer reasonable quantities and cooking order.
    - Output EXACTLY the structured guide with no additional text.
    """

    if client is None:
        return _fallback_recipe_nicely(raw_recipe)
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )
        return response.text or ""
    except Exception as e:
        print(f"DEBUG ERROR in format_recipe_nicely: {e}")
        return _fallback_recipe_nicely(raw_recipe)


def paraphrase_recipe(original_recipe: dict) -> dict:
    """
    Paraphrase a recipe to make it fresh while keeping the same ingredients and instructions.
    """
    prompt = f"""
    Paraphrase this recipe, keeping the exact same ingredients and instructions but rewording the title, description, and steps to make it sound fresh and unique.

    Original Recipe:
    Title: {original_recipe.get('title', '')}
    Description: {original_recipe.get('description', '')}
    Ingredients: {', '.join(original_recipe.get('ingredients', []))}
    Instructions: {'. '.join(original_recipe.get('instructions', []))}
    Prep Time: {original_recipe.get('prep_time', '30 mins')}
    Difficulty: {original_recipe.get('difficulty', 'Medium')}

    Output in this exact format:
    TITLE: [paraphrased title]
    DESCRIPTION: [paraphrased description]
    INGREDIENTS: [exact same ingredients, comma-separated]
    INSTRUCTIONS: [paraphrased steps, separated by dots]
    PREP_TIME: [same prep time]
    DIFFICULTY: [same difficulty]
    """

    if client is None:
        print("DEBUG: genai client not available for paraphrase; returning original")
        return original_recipe
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=f"{ZERO_SHOT_PERSONA}\n{prompt}"
        )
        response_text = (response.text or "").strip()
        parsed = _parse_generated_recipe(response_text)
        # Ensure ingredients and instructions are the same
        parsed['ingredients'] = original_recipe.get('ingredients', [])
        parsed['prep_time'] = original_recipe.get('prep_time', '30 mins')
        parsed['difficulty'] = original_recipe.get('difficulty', 'Medium')
        # Enforce monolithic single-sentence steps and normalized fields
        validated = _validate_generated_recipe(parsed, '')
        return validated
    except Exception as e:
        print(f"DEBUG ERROR in paraphrase_recipe: {e}")
        return original_recipe


def _normalize_restriction(restriction: str | None) -> str | None:
    if not restriction:
        return None
    value = str(restriction).strip().lower()
    if value in {"vegetarian", "vegan", "halal", "gluten-free", "gluten free", "gluten_free"}:
        if value in {"gluten free", "gluten_free"}:
            return "gluten-free"
        return value
    return None


def _recipe_matches_restriction(recipe: dict, restriction: str | None) -> bool:
    if not restriction:
        return True
    tags = [tag.lower() for tag in recipe.get('dietary_tags', []) if isinstance(tag, str)]
    if restriction == "vegetarian":
        return "vegetarian" in tags or "vegan" in tags
    return restriction in tags


def generate_new_recipe_from_query(user_query: str, recipe_samples: Optional[list] = None, restriction: Optional[str] = None) -> list[dict]:
    """
    If query is a recipe name, return the paraphrased recipe from dataset.
    If query is an ingredient, return paraphrased suggestions from dataset.
    """
    from services import recipe_service
    restriction_normalized = _normalize_restriction(restriction)
    all_recipes = recipe_service._load_all_recipes()
    validated_recipes = [r for r in all_recipes if recipe_service._validate_recipe_integrity(r) and _recipe_matches_restriction(r, restriction_normalized)]

    query_lower = user_query.lower().strip()
    query_text = _preprocess_query(user_query)
    is_ingredient_list = "," in query_text or any(unit in query_text.lower() for unit in ["cup", "tbsp", "tsp", "gram", "g", "kg", "ml", "l", "oz", "pound", "can", "slice", "slices"])
    query_label = "ingredient list" if is_ingredient_list else "dish name"
    print(f"DEBUG: generate_new_recipe_from_query query={query_lower!r} label={query_label} restriction={restriction_normalized}")

    # Check if query matches a recipe title exactly or by title inclusion.
    exact_matches = [r for r in validated_recipes if r.get('title', '').lower().strip() == query_lower]
    if exact_matches:
        recipe = exact_matches[0]
        print(f"DEBUG: exact title match found for query={query_lower!r}, using recipe {recipe.get('title')}")
        paraphrased = paraphrase_recipe(recipe)
        return [_ensure_recipe_contains_query_terms(paraphrased, query_text)]

    contains_title_matches = [r for r in validated_recipes if query_lower in r.get('title', '').lower()]
    if contains_title_matches:
        recipe = contains_title_matches[0]
        print(f"DEBUG: title contains match found for query={query_lower!r}, using recipe {recipe.get('title')}")
        paraphrased = paraphrase_recipe(recipe)
        return [_ensure_recipe_contains_query_terms(paraphrased, query_text)]

    # Assume it's an ingredient, find recipes containing it
    ingredient_recipes = []
    for r in validated_recipes:
        ingredients = [ing.lower().strip() for ing in r.get('ingredients', []) if isinstance(ing, str)]
        if any(re.search(rf'\b{re.escape(query_lower)}\b', ing) or query_lower in ing for ing in ingredients):
            ingredient_recipes.append(r)

    if ingredient_recipes:
        print(f"DEBUG: ingredient match found for query={query_lower!r}, returning {len(ingredient_recipes[:3])} recipes")
        # Take top 3, paraphrase each and enforce query terms
        top_3 = ingredient_recipes[:3]
        paraphrased_recipes = [_ensure_recipe_contains_query_terms(paraphrase_recipe(r), query_text) for r in top_3]
        return paraphrased_recipes

    # No matches, fall back to generating a new recipe
    # Use original logic
    query_text = _preprocess_query(user_query)
    if not query_text:
        return [_fallback_generated_recipe("")]

    is_ingredient_list = "," in query_text or any(unit in query_text.lower() for unit in ["cup", "tbsp", "tsp", "gram", "g", "kg", "ml", "l", "oz", "pound", "can", "slice", "slices"])
    query_label = "ingredient list" if is_ingredient_list else "dish name"

    if not recipe_samples:
        try:
            from rag import retriever
            recipe_samples = retriever.find_recipes_for_ingredients(query_text, top_k=3)
            recipe_samples = [r for r in recipe_samples if _recipe_matches_restriction(r, restriction_normalized)]
            print(f"DEBUG: RAG found {len(recipe_samples)} recipe samples for inspiration")
        except Exception as e:
            print(f"DEBUG: RAG sampling failed: {e}")
            recipe_samples = []

    context = _build_reference_prompt(query_text, recipe_samples)
    if recipe_samples:
        context += "\n" + _build_recipe_example()

    memory_context = _build_memory_learning_context(query_text)
    if memory_context:
        context += "\n" + memory_context

    restriction_prompt = ""
    if restriction_normalized:
        restriction_prompt = f"Follow this dietary restriction: {restriction_normalized}. Do not include ingredients that violate it.\n"
    
    base_prompt = f"""
    {ZERO_SHOT_PERSONA}
    You are a professional chef writing a completely original recipe.
    The user query is: {query_text}
    Query type: {query_label}
    {restriction_prompt}{context}

    If the query is a dish name, create a plausible recipe for that dish.
    If the query is an ingredient list, create a recipe that uses most of those ingredients.
    Add 2-3 complementary ingredients to balance flavor and texture.
    Use the user's query ingredient or dish name as the primary focus. If the query mentions beef, do not substitute chicken or another protein.

    IMPORTANT: Use reference recipes only as inspiration. Do not copy or reuse any exact ingredient list, recipe title, or instruction text from them.
    Create fresh steps, fresh wording, and a unique cooking approach.
    Do not repeat any ingredient or any cooking step.
    Do not use quotation marks anywhere in the ingredients or instructions.
    Each numbered instruction must be ONE monolithic natural-sounding sentence that synthesizes raw info into a single sentence; do not include multiple sentences, semicolons, or line breaks within a step.
    Each step must include timing in parentheses (e.g., "5 mins"). Do not break sentences because of commas.
    If the same query is used again, vary the result by changing the cooking method, seasoning, or presentation.

    Output EXACTLY in this format (no extra text, follow strictly):
    TITLE: [creative recipe name]
    DESCRIPTION: [1 sentence describing flavor and style]
    INGREDIENTS: [comma-separated list with quantities in a single line, for example: 250g beef, 1 tbsp soy sauce, 1 onion]
    INSTRUCTIONS: [8-10 numbered steps, each on its own line and each step one complete monolithic sentence with timing in parentheses, for example:
1. Heat oil in a pan (1 min).
2. Add beef and sear until golden (5 mins).]
    PREP_TIME: [total time like 45 mins or 1 hour]
    DIFFICULTY: [Easy, Medium, or Hard]
    """
    
    # Dynamically adjust prompt for Asian fusion if desired, or make it generic
    # For now, keeping the original "Asian fusion" instruction as it was in the context,
    # but it's a point of improvement.
    prompt = base_prompt

    if client is None:
        print("DEBUG: genai client not available; using fallback generator")
        return [_fallback_generated_recipe(query_text)]
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )
        response_text = (response.text or "").strip()
        print(f"DEBUG: Generated recipe response:\n{response_text}")
        parsed = _parse_generated_recipe(response_text)
        parsed = _validate_generated_recipe(parsed, query_text)
        parsed = _ensure_recipe_contains_query_terms(parsed, query_text)
        parsed = _enhance_recipe_quality(parsed, recipe_samples)
        return [parsed]
    except Exception as e:
        print(f"DEBUG ERROR in generate_new_recipe_from_query: {e}")
        return [_fallback_generated_recipe(query_text)]


def _parse_generated_recipe(response_text: str) -> dict:
    """
    Parse AI-generated recipe from structured text format.
    """
    lines = response_text.split('\n')
    recipe = {
        'title': 'New Recipe',
        'description': 'An original creation',
        'ingredients': [],
        'instructions': [],
        'prep_time': '30 mins',
        'difficulty': 'Medium',
        'is_generated': True
    }
    
    current_key = None
    raw_blocks = {
        'ingredients': [],
        'instructions': []
    }

    for line in lines:
        stripped = line.strip()
        # Handle potential markdown bolding like **TITLE:** and case variations
        clean_line = re.sub(r'[*_#]', '', stripped)
        if clean_line.upper().startswith('TITLE:'):
            recipe['title'] = clean_line.split(':', 1)[1].strip()
            current_key = 'title'
        elif clean_line.upper().startswith('DESCRIPTION:'):
            recipe['description'] = clean_line.split(':', 1)[1].strip()
            current_key = 'description'
        elif clean_line.upper().startswith('INGREDIENTS:'):
            raw_blocks['ingredients'].append(clean_line.split(':', 1)[1].strip())
            current_key = 'ingredients'
        elif clean_line.upper().startswith('INSTRUCTIONS:'):
            raw_blocks['instructions'].append(clean_line.split(':', 1)[1].strip())
            current_key = 'instructions'
        elif clean_line.upper().startswith('PREP_TIME:'):
            recipe['prep_time'] = clean_line.split(':', 1)[1].strip() or '30 mins'
            current_key = 'prep_time'
        elif clean_line.upper().startswith('DIFFICULTY:'):
            difficulty = clean_line.split(':', 1)[1].strip()
            recipe['difficulty'] = difficulty if difficulty in ['Easy', 'Medium', 'Hard'] else 'Medium'
            current_key = 'difficulty'
        elif current_key == 'ingredients':
            raw_blocks['ingredients'].append(stripped)
        elif current_key == 'instructions':
            raw_blocks['instructions'].append(stripped)

    recipe['ingredients'] = _parse_ingredients_list('\n'.join(raw_blocks['ingredients']))
    recipe['instructions'] = [_strip_quotes(step) for step in _split_instruction_steps('\n'.join(raw_blocks['instructions'])) if step]
    
    # Ensure ingredients and instructions are not empty
    if not recipe['ingredients']:
        recipe['ingredients'] = ['Ingredients to be determined']
    if not recipe['instructions']:
        recipe['instructions'] = ['Cook and combine all ingredients until done']
    
    return recipe


def _fallback_generated_recipe(user_ingredients: str) -> dict:
    """
    Fallback recipe when AI generation fails.
    """
    ingredients_list = [ing.strip() for ing in user_ingredients.split(',') if ing.strip()]

    estimated = [_estimate_ingredient_quantity(ing) for ing in ingredients_list]
    extras = ['2 tbsp soy sauce', '1 tbsp sesame oil', '2 cloves garlic', '1 tbsp ginger']
    ingredients = _dedupe_ordered(estimated + extras)

    raw_instructions = [
        f'Prepare and chop all {len(ingredients_list)} ingredients',
        'Heat oil in a large wok or pan over medium-high heat',
        'Add garlic and ginger, stir until fragrant',
        f'Add your ingredients and stir-fry until cooked',
        'Season with soy sauce and sesame oil',
        'Serve hot over rice or noodles'
    ]

    # Build minimal recipe for enforcement
    temp_recipe = {'ingredients': ingredients, 'instructions': raw_instructions}
    processed_instructions = _enforce_monolithic_instructions(temp_recipe)

    total_minutes = _estimate_total_cooking_time(ingredients)

    return {
        'title': 'Stir-Fried ' + (ingredients_list[0].capitalize() if ingredients_list else 'Delight'),
        'description': 'A quick and delicious fusion dish combining your ingredients',
        'ingredients': ingredients,
        'instructions': processed_instructions,
        'prep_time': f'{total_minutes} mins',
        'difficulty': 'Easy',
        'is_generated': True
    }
