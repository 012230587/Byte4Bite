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
from pathlib import Path

from dotenv import load_dotenv

from services.text_consolidation import (
    consolidate_raw_text_stream,
    instructions_look_fragmented,
    normalize_ingredient_list,
    normalize_instruction_list,
    sanitize_recipe_instructions,
)

# Ensure .env is loaded when this module is imported directly (tests, scripts)
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

API_KEY = os.getenv("GEMINI_API_KEY")
GENERATION_MODEL = "gemini-3-flash"
EMBEDDING_MODEL = "text-embedding-004"
MODEL_NAME = GENERATION_MODEL  # alias used across generate/format helpers

client = genai.Client(api_key=API_KEY) if (genai is not None and API_KEY) else None

# Persona: zero conversational filler, structured output only
ZERO_SHOT_PERSONA = (
    "You are an expert culinary assistant. Output ONLY the requested structured recipe format. "
    "Never include conversational filler such as 'Sure, here is your recipe', 'Certainly', "
    "or 'I hope you enjoy'. No preamble, no postscript."
)

# Stitching rule applied to all generation/format prompts (handles fragmented CSV source text)
STITCH_AND_FORMAT_RULES = """
FORMATTING RULES (mandatory):
- Source text may contain fragmented strings, broken line breaks, or erroneous inline time markers like '(2 mins)'.
  Remove all parenthetical minute markers; stitch fragments into unified sentences before outputting.
- INGREDIENTS: output as a clean bullet list (one ingredient per line, each starting with "• ").
- INSTRUCTIONS: output as a numbered chronological list (1. 2. 3. ...) of 5–6 clear cooking phases from prep through serving.
- Each step should be one focused phase (1–3 sentences) — never single-word fragments or timing-only lines.
- Do not repeat steps or ingredients. Do not use quotation marks in ingredients or steps.
"""

PANTRY_SECTION_RULES = """
[THE PANTRY] formatting directives (mandatory):
- Consolidate all fragmented text segments and parallel column remnants (e.g., hanging words like 'to serve') from the raw data context.
- Merge them into a single, unified, clean bulleted list (•) where quantity, units, and names are grouped strictly onto a single line per ingredient.
- Prohibit outputting ingredients across isolated or disjointed line breaks.
"""

# Staples to suggest when building a full ingredient list (fallback / prompt hints)
CUISINE_STAPLES = {
    "indian": ["2 tbsp oil", "1 tsp cumin seeds", "1 tsp garam masala", "salt", "fresh cilantro"],
    "italian": ["2 tbsp olive oil", "2 cloves garlic", "1 tsp dried oregano", "salt", "black pepper", "parmesan"],
    "mexican": ["2 tbsp oil", "1 tsp cumin", "1 lime", "fresh cilantro", "salt"],
    "chinese": ["2 tbsp vegetable oil", "2 tbsp soy sauce", "1 tbsp ginger", "2 cloves garlic", "1 tsp sesame oil"],
    "japanese": ["2 tbsp soy sauce", "1 tbsp mirin", "1 tbsp sake", "1 tbsp ginger"],
    "thai": ["2 tbsp oil", "1 tbsp fish sauce or tamari", "1 tbsp lime juice", "1 tsp sugar", "fresh basil"],
    "mediterranean": ["3 tbsp olive oil", "1 lemon", "2 cloves garlic", "dried oregano", "salt"],
    "american": ["2 tbsp butter or oil", "salt", "black pepper", "1 tbsp parsley"],
    "french": ["2 tbsp butter", "1 tbsp olive oil", "shallot", "fresh thyme", "salt"],
    "korean": ["2 tbsp sesame oil", "2 tbsp soy sauce", "1 tbsp gochujang or chili paste", "2 cloves garlic"],
    "middle eastern": ["2 tbsp olive oil", "1 tsp cumin", "1 tsp paprika", "lemon", "fresh parsley"],
}

SUPPORTED_CUISINES = list(CUISINE_STAPLES.keys()) + [
    "asian", "fusion", "british", "spanish", "greek", "vietnamese", "filipino", "pakistani",
]

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
    """Delegate to shared consolidation — binds fragmented lines with '; ' before list parsing."""
    return normalize_ingredient_list(ingredients_str)


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
    ingredients = normalize_ingredient_list(recipe.get("ingredients", []))
    instructions = normalize_instruction_list(recipe.get("instructions", []))

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


def _normalize_cuisine(cuisine: Optional[str]) -> str:
    if not cuisine:
        return ""
    value = str(cuisine).strip().lower()
    aliases = {
        "gluten free": "american",
        "south asian": "indian",
        "east asian": "chinese",
    }
    return aliases.get(value, value)


def _build_cuisine_prompt(cuisine: str) -> str:
    if not cuisine:
        return ""
    staples = CUISINE_STAPLES.get(cuisine, [])
    staple_hint = f" Typical staples for this cuisine: {', '.join(staples)}." if staples else ""
    return (
        f"Cook in authentic {cuisine.title()} style — techniques, seasoning, and flavor profile must match this cuisine.{staple_hint}"
    )


def _normalize_cooking_steps(recipe: dict, min_steps: int = 8) -> list[str]:
    """Light cleanup of already-stitched steps — do not re-split into fragments."""
    raw_steps = recipe.get("instructions", [])
    if isinstance(raw_steps, str):
        steps = normalize_instruction_list(raw_steps)
    elif isinstance(raw_steps, list) and raw_steps:
        steps = [str(step).strip() for step in raw_steps if str(step).strip()]
    else:
        steps = []

    processed: list[str] = []
    for step in steps:
        step_text = _clean_step_text(str(step))
        step_text = _TEMPORAL_MARKER_RE.sub("", step_text)
        step_text = re.sub(r"\s+", " ", step_text).strip()
        if not step_text:
            continue
        if step_text and step_text[-1] not in ".!?":
            step_text = f"{step_text}."
        processed.append(step_text)

    if processed:
        return _dedupe_ordered(processed)

    return [
        "Gather all ingredients and equipment on a clean work surface.",
        "Wash, peel, and slice vegetables; cut protein into even pieces.",
        "Preheat pan or oven as required for the dish.",
        "Cook aromatics in oil until fragrant.",
        "Add main ingredients and cook through with seasoning.",
        "Taste and adjust salt, acid, and spices.",
        "Plate with garnish and serve immediately.",
    ]


_TEMPORAL_MARKER_RE = re.compile(
    r"\(\s*\d+\s*(?:min|mins|minute|minutes|hour|hours|hr|hrs)\s*\)",
    re.IGNORECASE,
)


def stitch_recipe_instructions_with_llm(
    title: str,
    raw_instructions: Any,
    *,
    target_steps: int = 6,
) -> list[str]:
    """
    LLM stitching layer: merge sanitized fragments into logical numbered steps.
    Falls back to heuristic grouping when Gemini is unavailable.
    """
    raw_text = sanitize_recipe_instructions(raw_instructions)
    if not raw_text:
        return []

    if client is None:
        return normalize_instruction_list(raw_text)

    prompt = f"""You are a recipe editor. I have a raw, fragmented string of cooking instructions that contains
erroneous time markers like '(2 mins)'.
1. Remove all instances of '(X mins)' and similar parenthetical time markers.
2. Merge the fragments into coherent, full sentences.
3. Organize the text into a logical, numbered list of {target_steps} clear steps.
4. Each step should cover one cooking phase (1–3 sentences). Do not output single-word or timing-only lines.

Return ONLY a JSON array of strings — one string per step, no markdown, no numbering inside strings.

Recipe title: {title}
Raw Text: {raw_text}
"""

    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        response_text = (response.text or "").strip()
        if not response_text:
            return normalize_instruction_list(raw_text)

        parsed = _try_parse_json_value(response_text)
        if isinstance(parsed, list):
            steps = [
                _clean_step_text(_TEMPORAL_MARKER_RE.sub("", str(step)))
                for step in parsed
                if str(step).strip()
            ]
            steps = [_clean_step_text(s) for s in steps if _clean_step_text(s)]
            if steps:
                return _dedupe_ordered(steps)

        lines = [
            re.sub(r"^\s*\d+[\).]\s*", "", line).strip()
            for line in response_text.splitlines()
            if line.strip()
        ]
        lines = [_TEMPORAL_MARKER_RE.sub("", line) for line in lines if line]
        if lines:
            return _dedupe_ordered(lines)
    except Exception as exc:
        print(f"DEBUG: stitch_recipe_instructions_with_llm failed: {exc}")

    return normalize_instruction_list(raw_text)


def _validate_generated_recipe(
    recipe: dict,
    query_text: str,
    restrictions: Optional[list[str]] = None,
    cuisine: Optional[str] = None,
) -> dict:
    if not recipe.get("title"):
        recipe["title"] = "Chef Special Recipe"

    ingredients, instructions = _normalize_recipe_fields(recipe)
    if not ingredients:
        cuisine_key = _normalize_cuisine(cuisine)
        recipe["ingredients"] = CUISINE_STAPLES.get(cuisine_key, ["2 tbsp oil", "salt", "black pepper"])
    else:
        recipe["ingredients"] = [_estimate_ingredient_quantity(i) for i in ingredients]

    if not instructions:
        recipe["instructions"] = []
    else:
        recipe["instructions"] = instructions

    recipe["instructions"] = _normalize_cooking_steps(recipe)

    if not recipe.get("prep_time") or "min" not in str(recipe.get("prep_time", "")):
        total_minutes = _estimate_total_cooking_time(recipe["ingredients"])
        recipe["prep_time"] = f"{total_minutes} mins"

    if recipe.get("difficulty") not in ["Easy", "Medium", "Hard"]:
        recipe["difficulty"] = "Medium"

    normalized_restrictions = _normalize_restrictions(restrictions)
    if normalized_restrictions:
        recipe["dietary_tags"] = normalized_restrictions
    if cuisine:
        recipe["cuisine"] = _normalize_cuisine(cuisine)

    return recipe


def _build_recipe_example() -> str:
    return (
        "Example recipe format:\n"
        "TITLE: Velvet Coconut Lemongrass Chicken\n"
        "DESCRIPTION: A fragrant Thai-inspired dinner with bright citrus and creamy coconut balance.\n"
        "INGREDIENTS: 500g chicken thigh, 400ml coconut milk, 2 stalks lemongrass, 1 tbsp fish sauce, 1 lime, 2 tbsp oil, 1 onion, 2 cloves garlic, 1 thumb ginger, salt\n"
        "INSTRUCTIONS:\n"
        "1. Gather all ingredients, a large skillet, and a cutting board (3 mins).\n"
        "2. Slice chicken into bite-sized pieces and season lightly with salt (5 mins).\n"
        "3. Bruise lemongrass and finely chop onion, garlic, and ginger (5 mins).\n"
        "4. Heat oil in the skillet over medium-high heat until shimmering (2 mins).\n"
        "5. Sauté aromatics until fragrant and softened (3 mins).\n"
        "6. Add chicken and sear until lightly golden on the edges (8 mins).\n"
        "7. Pour in coconut milk, simmer until sauce thickens and chicken is cooked through (12 mins).\n"
        "8. Stir in fish sauce and lime juice, taste, and adjust seasoning (2 mins).\n"
        "9. Rest 2 minutes off heat so flavors settle (2 mins).\n"
        "10. Plate with fresh herbs and serve with steamed rice (2 mins).\n"
        "PREP_TIME: 45 mins\n"
        "DIFFICULTY: Medium\n"
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
    
    # Strip erroneous inline timing markers; keep prep_time on the recipe card instead.
    enhanced_instructions = []
    for instruction in instructions:
        instruction = re.sub(r'^\d+\.\s*', '', instruction).strip()
        instruction = _TEMPORAL_MARKER_RE.sub("", instruction).strip()
        instruction = instruction.rstrip('.')
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


def _enforce_monolithic_instructions(recipe: dict, restrictions: Optional[list[str]] = None) -> list[str]:
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

    restriction_note = ""
    if restrictions:
        normalized = _normalize_restrictions(restrictions)
        if normalized:
            restriction_note = f" Ensure this recipe strictly follows: {', '.join(normalized)}."

    processed = []
    for step in instructions:
        monolith = _make_monolithic_sentence(step + restriction_note, per_step)
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


def _ensure_recipe_contains_query_terms(
    recipe: dict,
    query_text: str,
    restrictions: Optional[list[str]] = None,
    cuisine: Optional[str] = None,
) -> dict:
    if not query_text or "," not in query_text:
        if _recipe_contains_query_terms(recipe, query_text) or not _extract_strong_query_ingredients(query_text):
            return recipe
    elif _recipe_contains_query_terms(recipe, query_text):
        return recipe

    print(f"DEBUG: Recipe missing pantry ingredients for query={query_text}; rebuilding fallback")
    return _fallback_generated_recipe(query_text, restrictions, cuisine)


def _filter_samples_by_cuisine(recipes: list, cuisine: str) -> list:
    if not cuisine or not recipes:
        return recipes
    needle = cuisine.lower()
    matched = []
    for recipe in recipes:
        meta = recipe.get("metadata") or {}
        haystack = " ".join([
            str(recipe.get("title", "")),
            str(recipe.get("description", "")),
            str(meta.get("cuisine", "")),
            str(meta.get("category", "")),
        ]).lower()
        if needle in haystack:
            matched.append(recipe)
    return matched if matched else recipes


def _build_complete_recipe_prompt(
    query_text: str,
    restrictions: Optional[list[str]],
    cuisine: str,
    recipe_samples: Optional[list],
) -> str:
    restriction_prompt = _build_restrictions_prompt(restrictions)
    cuisine_prompt = _build_cuisine_prompt(cuisine)
    context = _build_reference_prompt(query_text, recipe_samples or [])
    if recipe_samples:
        context += "\n" + _build_recipe_example()
    memory_context = _build_memory_learning_context(query_text)

    pantry_list = ", ".join([p.strip() for p in query_text.split(",") if p.strip()]) or query_text
    cuisine_line = cuisine_prompt or "Use a coherent international home-cooking style."

    return f"""
{ZERO_SHOT_PERSONA}
{STITCH_AND_FORMAT_RULES}
{PANTRY_SECTION_RULES}

Write one complete, original recipe for a home cook.

[THE PANTRY] (must use ALL of these): {pantry_list}
CUISINE: {cuisine_line}
{restriction_prompt}

{context}
{memory_context}

Requirements:
- TITLE: Unique, appetizing, specific name (not generic words like Stir-Fry, Delight, Bowl, or Chef Special).
- INGREDIENTS: Full list with precise quantities — pantry items PLUS oil, salt, aromatics, and cuisine-appropriate extras (8–14 items). Follow [THE PANTRY] directives above.
- INSTRUCTIONS: 10–14 numbered steps from gathering tools → washing/slicing → cooking → plating → serving.
- Paraphrase reference context in fresh wording; do not copy dataset text verbatim.
- Honor every dietary restriction.

Output EXACTLY this format (no extra text, no conversational filler):
TITLE: [name]
DESCRIPTION: [one sentence]
INGREDIENTS:
• [ingredient with quantity]
• [ingredient with quantity]
INSTRUCTIONS:
1. [complete step with timing]
2. [complete step with timing]
...
PREP_TIME: [total time]
DIFFICULTY: [Easy, Medium, or Hard]
"""


def _polish_generated_recipe(
    recipe: dict,
    query_text: str,
    restrictions: Optional[list[str]],
    cuisine: str,
) -> Optional[dict]:
    """Second pass: expand steps into a complete prep-to-serve flow."""
    if client is None:
        return None

    ingredients, instructions = _normalize_recipe_fields(recipe)
    restriction_prompt = _build_restrictions_prompt(restrictions)
    cuisine_prompt = _build_cuisine_prompt(cuisine)

    prompt = f"""
{ZERO_SHOT_PERSONA}
{STITCH_AND_FORMAT_RULES}
{PANTRY_SECTION_RULES}

Polish this draft into a publication-ready recipe. Rewrite everything freshly.

[THE PANTRY]: {query_text}
{cuisine_prompt}
{restriction_prompt}

Draft title: {recipe.get('title', '')}
Draft description: {recipe.get('description', '')}
Draft ingredients: {', '.join(ingredients)}
Draft steps (may be fragmented — stitch into coherent steps): {' '.join(instructions)}

Output EXACTLY (no filler text):
TITLE: [unique title]
DESCRIPTION: [one sentence]
INGREDIENTS:
• [quantity + ingredient]
INSTRUCTIONS:
1. [gather/prep step with timing]
...
10-14. [serve step with timing]
PREP_TIME: [total]
DIFFICULTY: [Easy/Medium/Hard]
"""

    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        response_text = (response.text or "").strip()
        if not response_text:
            return None
        parsed = _parse_generated_recipe(response_text)
        return _validate_generated_recipe(parsed, query_text, restrictions, cuisine)
    except Exception as e:
        print(f"DEBUG ERROR in _polish_generated_recipe: {e}")
        return None


def _generate_custom_recipe(
    query_text: str,
    restrictions: Optional[list[str]],
    cuisine: str,
    recipe_samples: Optional[list],
) -> dict:
    cuisine_norm = _normalize_cuisine(cuisine) or "fusion"
    prompt = _build_complete_recipe_prompt(query_text, restrictions, cuisine_norm, recipe_samples)

    if client is None:
        return _fallback_generated_recipe(query_text, restrictions, cuisine_norm)

    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        response_text = (response.text or "").strip()
        parsed = _parse_generated_recipe(response_text)
        parsed = _validate_generated_recipe(parsed, query_text, restrictions, cuisine_norm)
        parsed = _ensure_recipe_contains_query_terms(parsed, query_text, restrictions, cuisine_norm)
        parsed = _enhance_recipe_quality(parsed, recipe_samples)
        parsed["is_generated"] = True

        polished = _polish_generated_recipe(parsed, query_text, restrictions, cuisine_norm)
        if polished:
            polished["is_generated"] = True
            polished = _ensure_recipe_contains_query_terms(polished, query_text, restrictions, cuisine_norm)
            return polished
        return parsed
    except Exception as e:
        print(f"DEBUG ERROR in _generate_custom_recipe: {e}")
        return _fallback_generated_recipe(query_text, restrictions, cuisine_norm)


def adjust_recipe_for_restrictions(recipe: dict, restrictions: Optional[list[str]] = None) -> str:
    title = recipe.get('title', 'Unknown Dish')
    ingredients, instructions = _normalize_recipe_fields(recipe)
    restrictions_prompt = _build_restrictions_prompt(restrictions)
    prompt = f"""
    {ZERO_SHOT_PERSONA}
    {STITCH_AND_FORMAT_RULES}
    {PANTRY_SECTION_RULES}

    Format this recipe for a premium cooking app: {title}.
    Ingredients: {ingredients}
    Instructions (may be fragmented — stitch into unified steps): {instructions}
    {restrictions_prompt}

    Output structure (no conversational filler):
    INTRO: [one sentence on flavor and total time]
    INGREDIENTS:
    • [quantity + ingredient per line]
    INSTRUCTIONS:
    1. [numbered step with timing]
    ...
    CHEF_TIP: [one practical tip]
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
    restrictions_prompt = _build_restrictions_prompt(raw_recipe.get('dietary_restrictions') or raw_recipe.get('restrictions'))

    prompt = f"""
    {ZERO_SHOT_PERSONA}
    {STITCH_AND_FORMAT_RULES}
    {PANTRY_SECTION_RULES}

    Rewrite this recipe into a professional cooking guide.

    Dish: {title}
    Description: {description}
    Ingredients: {ingredients}
    Instructions (stitch fragments): {instructions}
    Prep Time: {raw_recipe.get('prep_time', 'Unknown')}
    {restrictions_prompt}

    Output EXACTLY (no filler):
    INTRO: [one sentence]
    INGREDIENTS:
    • [item per line with quantity]
    INSTRUCTIONS:
    1. [step with timing]
    ...
    TOTAL_TIME: [prep_time]
    CHEF_TIP: [one tip]
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
    Rewrite a dataset recipe with fresh wording and complete prep-to-serve steps.
    """
    prompt = f"""
    Rewrite this recipe with a unique title and fully detailed steps from washing/slicing ingredients through plating and serving.
    Keep the same core ingredients but you may add quantities where missing.

    Original Recipe:
    Title: {original_recipe.get('title', '')}
    Description: {original_recipe.get('description', '')}
    Ingredients: {', '.join(original_recipe.get('ingredients', []))}
    Instructions: {'. '.join(original_recipe.get('instructions', []))}
    Prep Time: {original_recipe.get('prep_time', '30 mins')}
    Difficulty: {original_recipe.get('difficulty', 'Medium')}

    Output in this exact format:
    TITLE: [unique paraphrased title]
    DESCRIPTION: [paraphrased description]
    INGREDIENTS: [comma-separated with quantities]
    INSTRUCTIONS:
    1. [prep step with timing]
    ...
    PREP_TIME: [prep time]
    DIFFICULTY: [difficulty]
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
        parsed['prep_time'] = original_recipe.get('prep_time', parsed.get('prep_time', '30 mins'))
        parsed['difficulty'] = original_recipe.get('difficulty', parsed.get('difficulty', 'Medium'))
        validated = _validate_generated_recipe(
            parsed, "", restrictions=None, cuisine=original_recipe.get("cuisine")
        )
        validated['is_generated'] = True
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


def _normalize_restrictions(restrictions: Optional[list[str]] = None) -> list[str]:
    if not restrictions:
        return []
    normalized = []
    for item in restrictions:
        if isinstance(item, str):
            normalized_value = _normalize_restriction(item)
            if normalized_value and normalized_value not in normalized:
                normalized.append(normalized_value)
    return normalized


def _build_restrictions_prompt(restrictions: Optional[list[str]] = None) -> str:
    normalized = _normalize_restrictions(restrictions)
    if not normalized:
        return ""
    return (
        "Strictly follow these dietary restrictions: "
        + ", ".join(normalized)
        + ". Do not include any prohibited ingredients, preparation methods, or seasoning that violates them."
    )


def _recipe_matches_restrictions(recipe: dict, restrictions: Optional[list[str]] = None) -> bool:
    normalized = _normalize_restrictions(restrictions)
    if not normalized:
        return True
    tags = [tag.lower() for tag in recipe.get('dietary_tags', []) if isinstance(tag, str)]
    for restriction in normalized:
        if restriction == "vegetarian":
            if not ("vegetarian" in tags or "vegan" in tags):
                return False
        elif restriction == "vegan":
            if "vegan" not in tags:
                return False
        else:
            if restriction not in tags:
                return False
    return True


def generate_new_recipe_from_query(
    user_query: str,
    recipe_samples: Optional[list] = None,
    restrictions: Optional[list[str]] = None,
    cuisine: Optional[str] = None,
) -> list[dict]:
    """
    Build one complete original recipe from pantry ingredients, dietary restrictions, and cuisine.
    Uses RAG samples for inspiration only — output is always freshly written.
    """
    restriction_normalized = _normalize_restrictions(restrictions)
    cuisine_normalized = _normalize_cuisine(cuisine) or "fusion"
    query_text = _preprocess_query(user_query)

    if not query_text:
        return [_fallback_generated_recipe("", restriction_normalized, cuisine_normalized)]

    print(
        f"DEBUG: generate_new_recipe_from_query query={query_text!r} "
        f"cuisine={cuisine_normalized} restrictions={restriction_normalized}"
    )

    if not recipe_samples:
        try:
            from rag import retriever
            recipe_samples = retriever.find_recipes_for_ingredients(query_text, top_k=5)
            recipe_samples = [
                r for r in recipe_samples
                if _recipe_matches_restrictions(r, restriction_normalized)
            ]
            recipe_samples = _filter_samples_by_cuisine(recipe_samples, cuisine_normalized)
            print(f"DEBUG: RAG found {len(recipe_samples)} cuisine-aware samples")
        except Exception as e:
            print(f"DEBUG: RAG sampling failed: {e}")
            recipe_samples = []

    recipe = _generate_custom_recipe(
        query_text, restriction_normalized, cuisine_normalized, recipe_samples
    )
    return [recipe]


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
            cleaned = re.sub(r'^[\s•\-\*]+', '', stripped)
            if cleaned:
                raw_blocks['ingredients'].append(cleaned)
        elif current_key == 'instructions':
            raw_blocks['instructions'].append(stripped)

    ing_block = consolidate_raw_text_stream(raw_blocks['ingredients'])
    recipe['ingredients'] = normalize_ingredient_list(ing_block)
    inst_block = consolidate_raw_text_stream(raw_blocks['instructions'])
    recipe['instructions'] = [_strip_quotes(step) for step in normalize_instruction_list(inst_block) if step]
    
    # Ensure ingredients and instructions are not empty
    if not recipe['ingredients']:
        recipe['ingredients'] = ['Ingredients to be determined']
    if not recipe['instructions']:
        recipe['instructions'] = ['Cook and combine all ingredients until done']
    
    return recipe


def _fallback_generated_recipe(
    user_ingredients: str,
    restrictions: Optional[list[str]] = None,
    cuisine: Optional[str] = None,
) -> dict:
    """Fallback recipe when AI generation fails — still uses full prep-to-serve steps."""
    ingredients_list = [ing.strip() for ing in user_ingredients.split(",") if ing.strip()]
    normalized_restrictions = _normalize_restrictions(restrictions)
    cuisine_key = _normalize_cuisine(cuisine) or "fusion"

    estimated = [_estimate_ingredient_quantity(ing) for ing in ingredients_list]
    extras = list(CUISINE_STAPLES.get(cuisine_key, ["2 tbsp oil", "salt", "black pepper"]))
    if "gluten-free" in normalized_restrictions:
        extras = [e.replace("soy sauce", "tamari") for e in extras]
    if "vegan" in normalized_restrictions:
        extras = [e for e in extras if "fish sauce" not in e.lower()]

    ingredients = _dedupe_ordered(estimated + extras)
    main_item = ingredients_list[0].capitalize() if ingredients_list else "Pantry"

    raw_instructions = [
        "Gather all ingredients, cutting board, knife, and a large skillet or pot (3 mins).",
        f"Wash and pat dry produce; peel and slice aromatics; cut {main_item} into even bite-sized pieces (10 mins).",
        "Measure sauces and spices into small bowls so they are ready to add (3 mins).",
        "Heat oil in the skillet over medium-high heat until it shimmers (2 mins).",
        "Sauté garlic and ginger until fragrant but not browned (2 mins).",
        f"Add {main_item} and harder vegetables; cook until lightly golden and nearly tender (10 mins).",
        "Add any quick-cooking items and sauce; toss to coat and simmer until everything is cooked through (8 mins).",
        "Taste and adjust salt, acid, and spice to balance the dish (2 mins).",
        "Remove from heat and rest 2 minutes so flavors meld (2 mins).",
        "Transfer to warm plates, garnish with fresh herbs if available, and serve immediately (2 mins).",
    ]

    temp_recipe = {"ingredients": ingredients, "instructions": raw_instructions}
    processed_instructions = _normalize_cooking_steps(temp_recipe)
    total_minutes = _estimate_total_cooking_time(ingredients)

    title_seed = ingredients_list[0] if ingredients_list else "Pantry"
    cuisine_title = cuisine_key.title() if cuisine_key != "fusion" else "Heritage"
    title = f"{cuisine_title} {title_seed} Skillet Supper"

    return {
        "title": title,
        "description": f"A complete {cuisine_key} home-cooked dish built from your pantry with balanced seasoning.",
        "ingredients": ingredients,
        "instructions": processed_instructions,
        "prep_time": f"{total_minutes} mins",
        "difficulty": "Easy",
        "is_generated": True,
        "cuisine": cuisine_key,
        "dietary_tags": normalized_restrictions,
    }
