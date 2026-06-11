"""
Technique-based recipe templates for quota-off / no-LLM fallbacks.

Used when Gemini is unavailable and corpus adaptation yields thin steps.
Templates follow dry / moist / combination heat patterns aligned with the dataset.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# Mirrors ai_service.CUISINE_STAPLES (kept here to avoid circular imports)
CUISINE_STAPLES: dict[str, list[str]] = {
    "indian": ["2 tbsp oil", "1 tsp cumin seeds", "1 tsp garam masala", "salt", "fresh cilantro"],
    "italian": ["2 tbsp olive oil", "2 cloves garlic", "1 tsp dried oregano", "salt", "black pepper"],
    "mexican": ["2 tbsp oil", "1 tsp cumin", "1 lime", "fresh cilantro", "salt"],
    "chinese": ["2 tbsp vegetable oil", "2 tbsp soy sauce", "1 tbsp ginger", "2 cloves garlic"],
    "japanese": ["2 tbsp soy sauce", "1 tbsp mirin", "1 tbsp sake", "1 tbsp ginger"],
    "thai": ["2 tbsp oil", "1 tbsp fish sauce or tamari", "1 tbsp lime juice", "1 tsp sugar"],
    "mediterranean": ["3 tbsp olive oil", "1 lemon", "2 cloves garlic", "dried oregano", "salt"],
    "american": ["2 tbsp butter or oil", "salt", "black pepper", "1 tbsp parsley"],
    "french": ["2 tbsp butter", "1 tbsp olive oil", "shallot", "fresh thyme", "salt"],
    "korean": ["2 tbsp sesame oil", "2 tbsp soy sauce", "1 tbsp gochujang", "2 cloves garlic"],
    "middle eastern": ["2 tbsp olive oil", "1 tsp cumin", "1 tsp paprika", "lemon", "fresh parsley"],
    "pakistani": ["2 tbsp ghee or oil", "1 tbsp ginger-garlic paste", "1 tsp cumin", "garam masala", "salt"],
    "greek": ["3 tbsp olive oil", "1 lemon", "oregano", "garlic", "salt"],
    "spanish": ["2 tbsp olive oil", "1 tsp smoked paprika", "garlic", "salt"],
    "vietnamese": ["2 tbsp oil", "1 tbsp fish sauce or tamari", "lime", "garlic", "fresh herbs"],
    "filipino": ["2 tbsp oil", "2 tbsp soy sauce", "garlic", "vinegar", "black pepper"],
}

PROTEIN_PATTERNS: list[tuple[str, str]] = [
    (r"\b(chicken|poultry|thigh|breast|drumstick)\b", "chicken"),
    (r"\b(beef|steak|sirloin|brisket|mince|ground beef)\b", "beef"),
    (r"\b(lamb|mutton)\b", "lamb"),
    (r"\b(pork|bacon|ham)\b", "pork"),
    (r"\b(fish|salmon|cod|tilapia|prawn|shrimp)\b", "fish"),
    (r"\b(tofu|paneer)\b", "tofu"),
]

METHOD_RULES: list[tuple[str, str]] = [
    (r"\b(stir[\s-]?fry|wok)\b", "stir_fry"),
    (r"\b(grill(?:ed|ing)?|bbq|barbecue|char(?:red)?)\b", "grill"),
    (r"\b(boil(?:ed|ing)?|poach(?:ed|ing)?)\b", "moist_boil_poach"),
    (r"\b(brais(?:e|ed|ing)?|stew(?:ed|ing)?|curry|haleem|tagine)\b", "braise_stew"),
    (r"\b(roast(?:ed|ing)?|bake(?:d|ing)?|oven)\b", "roast_bake"),
    (r"\b(steam(?:ed|ing)?)\b", "steam"),
    (r"\b(sauce|gravy|soup|broth|simmer|curry)\b", "sauce_simmer"),
    (r"\b(fry|fried|saut[eé]|pan[\s-]?fry|skillet)\b", "pan_fry_saute"),
]

METHOD_DEFAULT_BY_PROTEIN = {
    "chicken": "sauce_simmer",
    "beef": "braise_stew",
    "lamb": "braise_stew",
    "fish": "steam",
    "tofu": "stir_fry",
    "pork": "pan_fry_saute",
}

METHOD_TEMPLATES: dict[str, list[str]] = {
    "sauce_simmer": [
        "Prep {protein} into even pieces and chop {aromatics}; measure {liquid} and {seasoning}.",
        "Heat oil in a deep pan over medium-high heat and sauté {aromatics} until fragrant and softened.",
        "Add {protein} and cook until lightly coloured on all sides.",
        "Pour in {liquid} with {seasoning}; stir and bring to a gentle simmer.",
        "Partially cover and simmer until {protein} is cooked through and the sauce coats the back of a spoon.",
        "Rest off heat for 2 minutes, adjust salt and acid, then serve with {side}.",
    ],
    "grill": [
        "Pat {protein} dry, season with {seasoning}, and rest at room temperature for 10 minutes.",
        "Preheat a grill or grill pan over high heat and lightly oil the grates.",
        "Grill {protein} without moving until char lines form, then flip once.",
        "Cook to desired doneness — for beef steaks about 3–4 minutes per side for medium.",
        "Transfer to a plate, tent with foil, and rest 5 minutes before slicing against the grain.",
        "Serve with {side} and any resting juices.",
    ],
    "moist_boil_poach": [
        "Bring {liquid} to a boil in a wide pot; season generously with salt and {seasoning}.",
        "Reduce to a gentle simmer and slide in {protein} so it is mostly submerged.",
        "Poach or boil until {protein} is opaque and tender throughout.",
        "Remove {protein} to a board; reserve a cup of cooking liquid if making a light sauce.",
        "Slice or shred {protein}; moisten with a little cooking liquid or {seasoning}.",
        "Serve warm with {side} or toss into a salad.",
    ],
    "stir_fry": [
        "Cut {protein} and any vegetables into uniform bite-sized pieces; mix {seasoning} with a splash of soy or oil.",
        "Heat a wok or large skillet over high heat until very hot, then add oil.",
        "Stir-fry {protein} until just cooked; transfer to a plate.",
        "Stir-fry harder vegetables first, then softer ones and {aromatics}.",
        "Return {protein} to the pan, add sauce, and toss 1–2 minutes until glossy and piping hot.",
        "Serve immediately over {side}.",
    ],
    "braise_stew": [
        "Brown {protein} in oil over medium-high heat; set aside.",
        "In the same pot, sauté {aromatics} with {seasoning} until fragrant.",
        "Deglaze with a splash of {liquid}, scraping up any browned bits.",
        "Return {protein}, add enough {liquid} to come halfway up the meat, and bring to a simmer.",
        "Cover and cook on low until {protein} is fork-tender and the liquid has thickened into a rich sauce.",
        "Adjust seasoning and serve with {side}.",
    ],
    "roast_bake": [
        "Preheat the oven to 200°C (400°F). Season {protein} inside and out with {seasoning}.",
        "Optional: sear {protein} in an oven-safe pan for colour, then transfer to the oven.",
        "Roast until cooked through and golden — chicken pieces about 35–50 minutes depending on size.",
        "Baste with pan juices once or twice during roasting.",
        "Rest {protein} 10 minutes before carving or slicing.",
        "Serve with {side} and pan juices.",
    ],
    "steam": [
        "Set up a steamer basket over boiling water.",
        "Season {protein} with {seasoning} and arrange in a single layer in the steamer.",
        "Steam until just cooked through — fish fillets about 8–12 minutes, chicken pieces longer.",
        "Optional: finish with hot oil and {aromatics} or a light drizzle of soy and lime.",
        "Transfer carefully to plates.",
        "Serve with {side}.",
    ],
    "pan_fry_saute": [
        "Prep and season {protein}; chop {aromatics} and any vegetables from your pantry.",
        "Heat oil in a large skillet over medium-high heat until shimmering.",
        "Sauté {aromatics} until softened, then add {protein} and cook until golden and nearly done.",
        "Add quick-cooking vegetables or a splash of {liquid}; toss to coat.",
        "Simmer briefly until everything is cooked through and lightly sauced.",
        "Taste, adjust {seasoning}, and serve with {side}.",
    ],
}

SIDE_BY_CUISINE = {
    "indian": "steamed basmati rice or flatbread",
    "italian": "pasta or crusty bread",
    "mexican": "warm tortillas or rice",
    "chinese": "jasmine rice",
    "japanese": "steamed rice",
    "thai": "jasmine rice",
    "pakistani": "naan or steamed rice",
    "mediterranean": "couscous or roasted vegetables",
    "american": "mashed potatoes or rice",
}


def detect_cooking_method(query_text: str, restrictions: Optional[list[str]] = None) -> str:
    q = (query_text or "").lower()
    for pattern, method in METHOD_RULES:
        if re.search(pattern, q, re.I):
            return method
    protein = detect_protein(q, restrictions)
    return METHOD_DEFAULT_BY_PROTEIN.get(protein, "pan_fry_saute")


def detect_protein(query_text: str, restrictions: Optional[list[str]] = None) -> str:
    q = (query_text or "").lower()
    normalized = [r.lower() for r in (restrictions or [])]
    skip_pork = "halal" in normalized or "vegan" in normalized
    for pattern, name in PROTEIN_PATTERNS:
        if skip_pork and name == "pork":
            continue
        if re.search(pattern, q, re.I):
            return name
    if re.search(r"\b(sauce|gravy|soup)\b", q) and "chicken" not in q:
        return "chicken"  # sensible default for sauce dishes
    return "chicken"


def _estimate_quantity(item: str) -> str:
    item = item.strip()
    if not item:
        return item
    if re.search(r"\d|cup|tbsp|tsp|g|kg|ml|lb|oz|clove|pinch", item, re.I):
        return item
    return f"1 portion {item}"


def _normalize_cuisine(cuisine: Optional[str]) -> str:
    if not cuisine:
        return "fusion"
    value = str(cuisine).strip().lower()
    return value if value in CUISINE_STAPLES or value in SIDE_BY_CUISINE else "fusion"


def _liquid_for_method(method: str, protein: str, cuisine: str) -> str:
    if method == "moist_boil_poach":
        return "water or light stock with bay leaf and peppercorns"
    if method in {"sauce_simmer", "braise_stew"}:
        if protein == "beef":
            return "beef stock or water"
        if protein == "chicken":
            return "chicken stock or coconut milk for curry-style dishes"
        return "stock or water"
    if method == "stir_fry":
        return "2 tbsp soy sauce mixed with 1 tbsp water"
    return "1/2 cup stock or water"


def _query_pantry_terms(query_text: str) -> list[str]:
    """Split query into pantry terms — comma list or dish-style tokens."""
    if "," in query_text:
        return [p.strip() for p in query_text.split(",") if p.strip()]
    q = query_text.strip()
    if not q:
        return []
    # Multi-word dish: "chicken sauce", "beef stir fry"
    return [q]


def _protein_display(query_text: str, restrictions: Optional[list[str]] = None) -> str:
    protein_key = detect_protein(query_text, restrictions)
    labels = {
        "chicken": "500 g chicken pieces",
        "beef": "500 g beef strips or cubes",
        "lamb": "500 g lamb pieces",
        "pork": "500 g pork pieces",
        "fish": "400 g fish fillets",
        "tofu": "400 g firm tofu, cubed",
    }
    base = labels.get(protein_key, "500 g main protein")

    pantry = _query_pantry_terms(query_text)
    if pantry and "," in query_text:
        first = pantry[0]
        if re.search(r"\d|cup|tbsp|g|kg|ml", first, re.I):
            return _estimate_quantity(first)
        if protein_key in first.lower() or any(
            k in first.lower() for k in ("chicken", "beef", "fish", "tofu", "lamb", "pork")
        ):
            return _estimate_quantity(first) if len(first.split()) <= 3 else base
    return base


def build_template_context(
    query_text: str,
    cuisine: Optional[str] = None,
    restrictions: Optional[list[str]] = None,
) -> dict[str, str]:
    cuisine_key = _normalize_cuisine(cuisine)
    pantry_items = _query_pantry_terms(query_text)
    protein = _protein_display(query_text, restrictions)
    protein_key = detect_protein(query_text, restrictions)

    staples = CUISINE_STAPLES.get(cuisine_key, CUISINE_STAPLES.get("american", []))
    aromatics = ", ".join(
        s for s in staples if any(k in s.lower() for k in ("garlic", "ginger", "onion", "shallot"))
    )
    if not aromatics:
        aromatics = "onion and garlic"

    method = detect_cooking_method(query_text, restrictions)
    liquid = _liquid_for_method(method, protein_key, cuisine_key)
    seasoning = ", ".join(s for s in staples if "salt" in s.lower() or "pepper" in s.lower() or "masala" in s.lower() or "cumin" in s.lower())
    if not seasoning:
        seasoning = "salt and black pepper"

    if restrictions:
        if "gluten-free" in [r.lower() for r in restrictions]:
            liquid = liquid.replace("soy sauce", "tamari")
        if "vegan" in [r.lower() for r in restrictions]:
            protein = protein.replace("chicken", "tofu").replace("beef", "tofu")
            liquid = "vegetable stock"

    side = SIDE_BY_CUISINE.get(cuisine_key, "steamed rice or bread")
    if any("rice" in p.lower() for p in pantry_items):
        side = "the prepared rice"
    cuisine_adj = f"{cuisine_key.title()}-style" if cuisine_key != "fusion" else "home-style"

    return {
        "protein": protein,
        "aromatics": aromatics,
        "liquid": liquid,
        "seasoning": seasoning,
        "side": side,
        "cuisine_adj": cuisine_adj,
        "pantry": ", ".join(pantry_items) if pantry_items else query_text,
        "method": method,
        "cuisine": cuisine_key,
    }


def fill_method_template(method: str, context: dict[str, str]) -> list[str]:
    steps = METHOD_TEMPLATES.get(method) or METHOD_TEMPLATES["pan_fry_saute"]
    filled: list[str] = []
    for step in steps:
        try:
            filled.append(step.format(**context))
        except KeyError:
            filled.append(step)
    return filled


def merge_corpus_and_template(
    corpus_steps: list[str],
    template_steps: list[str],
    *,
    min_steps: int = 5,
    max_steps: int = 6,
) -> list[str]:
    """Prefer corpus technique steps; pad with template phases when corpus is thin."""
    if len(corpus_steps) >= min_steps:
        return corpus_steps[:max_steps]

    seen = {s.lower().strip() for s in corpus_steps}
    merged = list(corpus_steps)
    for step in template_steps:
        key = step.lower().strip()
        if key not in seen:
            merged.append(step)
            seen.add(key)
        if len(merged) >= max_steps:
            break
    return merged[:max_steps]


def build_method_fallback_recipe(
    query_text: str,
    cuisine: Optional[str] = None,
    restrictions: Optional[list[str]] = None,
    *,
    corpus_steps: Optional[list[str]] = None,
    inspired_title: Optional[str] = None,
    compose_mode: str = "method_template",
    compose_reason: str = "llm_unavailable",
) -> dict[str, Any]:
    """Build a sensible technique-based recipe while Gemini quota is exhausted."""
    context = build_template_context(query_text, cuisine, restrictions)
    method = context["method"]
    template_steps = fill_method_template(method, context)

    if corpus_steps:
        instructions = merge_corpus_and_template(corpus_steps, template_steps)
        mode = "corpus_hybrid"
    else:
        instructions = template_steps
        mode = compose_mode

    pantry_items = [p.strip() for p in query_text.split(",") if p.strip()]
    estimated = [_estimate_quantity(p) for p in pantry_items] if pantry_items else []
    staples = CUISINE_STAPLES.get(context["cuisine"], CUISINE_STAPLES["american"])
    ingredients = list(dict.fromkeys(estimated + staples[:4]))[:14]

    dish = query_text.strip().title() or "Pantry Dish"
    method_label = method.replace("_", " ")
    title = f"{dish} ({method_label})"
    if context["cuisine"] != "fusion":
        title = f"{dish} — {context['cuisine_adj'].replace('-style', '').strip()} ({method_label})"

    desc = f"A {context['cuisine_adj']} {method.replace('_', ' ')} dish built from your pantry"
    if inspired_title:
        desc += f", guided by corpus match «{inspired_title}»."
    else:
        desc += " using standard culinary technique while AI rewriting is paused."

    cook_times = {
        "grill": 25,
        "stir_fry": 20,
        "moist_boil_poach": 30,
        "sauce_simmer": 35,
        "braise_stew": 75,
        "roast_bake": 55,
        "steam": 20,
        "pan_fry_saute": 30,
    }

    return {
        "title": title,
        "description": desc,
        "ingredients": ingredients,
        "instructions": instructions,
        "prep_time": f"{cook_times.get(method, 30)} mins",
        "difficulty": "Medium" if method in {"braise_stew", "roast_bake"} else "Easy",
        "is_generated": True,
        "cuisine": context["cuisine"],
        "cooking_method": method,
        "compose_mode": mode,
        "compose_reason": compose_reason,
    }
