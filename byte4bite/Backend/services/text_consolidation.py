"""
Text consolidation for fragmented CSV/dataset fields.

Data flow:
  raw cell text  ->  consolidate_raw_text_stream()  (bind lines with '; ')
                 ->  split + merge fragments         ->  list[str] for API/DB
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any

# Hanging column remnants often split onto their own line in messy datasets
COLUMN_REMNANTS = {
    "to serve",
    "for serving",
    "to garnish",
    "for garnish",
    "to taste",
    "as needed",
    "optional",
    "for topping",
    "to finish",
    "for decoration",
    "to decorate",
    "for serving",
    "garnish",
    "serve",
}

SEPARATOR = "; "


def looks_like_python_list(text: Any) -> bool:
    """True when a CSV cell looks like `['item 1', 'item 2, with comma']`."""
    if not isinstance(text, str):
        return False
    stripped = text.strip()
    return bool(stripped) and stripped.startswith("[") and stripped.endswith("]")


def parse_python_style_list(text: Any) -> list[str] | None:
    """
    Safely parse Python-style list cells from datasets.

    Uses ast.literal_eval first so commas inside quoted ingredients
    (e.g. '1 garlic clove, pressed or finely chopped') stay intact.
    Falls back to json.loads for double-quoted JSON arrays.
    """
    if isinstance(text, list):
        return [str(item).strip() for item in text if item is not None and str(item).strip()]
    if not isinstance(text, str):
        return None

    stripped = text.strip()
    if not stripped or not looks_like_python_list(stripped):
        return None

    # ast.literal_eval understands single-quoted Python list syntax in Food Ingredients CSV
    for parser in (ast.literal_eval, json.loads):
        try:
            parsed = parser(stripped)
            if isinstance(parsed, list):
                return [
                    str(item).strip()
                    for item in parsed
                    if item is not None and str(item).strip()
                ]
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
        except Exception:
            continue
    return None


# Internal alias kept for existing call sites
_try_parse_list_literal = parse_python_style_list


def _unwrap_horizontal_columns(line: str) -> str:
    """
    Repair one-line horizontal two-column reads from blind PDF extractors,
    e.g. '3/4 cup pecans    toasted' -> '3/4 cup pecans, toasted'.
    """
    parts = [part.strip() for part in re.split(r"[\t]| {3,}", line.strip()) if part.strip()]
    if len(parts) != 2:
        return line.strip()

    left, right = parts[0], parts[1]
    if _looks_like_continuation(right) or _is_column_remnant(right) or len(right.split()) <= 3:
        return f"{left}, {right}"
    return line.strip()


def consolidate_raw_text_stream(raw: Any) -> str:
    """
    Intercept a raw text stream: strip whitespace, drop empties, join lines with '; '.
    Produces one cohesive block before list parsing.
    """
    if raw is None:
        return ""

    literal_items = parse_python_style_list(raw)
    if literal_items:
        return SEPARATOR.join(literal_items)

    if isinstance(raw, list):
        lines: list[str] = []
        for item in raw:
            if item is None:
                continue
            text = str(item).replace("\r\n", "\n").replace("\r", "\n")
            for segment in text.split("\n"):
                segment = _unwrap_horizontal_columns(segment)
                if segment:
                    lines.append(segment)
        return SEPARATOR.join(lines)

    text = str(raw).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""

    lines = [_unwrap_horizontal_columns(line) for line in text.split("\n") if line.strip()]
    if not lines:
        return ""

    return SEPARATOR.join(lines)


def _strip_quotes(text: str) -> str:
    cleaned = str(text).strip().strip('"').strip("'")
    return cleaned.replace("\u201c", "").replace("\u201d", "").strip()


def _is_column_remnant(text: str) -> bool:
    lowered = text.lower().strip().rstrip(".")
    if lowered in COLUMN_REMNANTS:
        return True
    if len(lowered.split()) <= 3 and lowered.startswith(("to ", "for ", "as ")):
        return True
    return False


def _looks_like_continuation(text: str) -> bool:
    """Short tail fragment without quantity, e.g. 'sifted', 'finely chopped'."""
    if re.search(r"\d", text):
        return False
    words = text.split()
    if len(words) > 4:
        return False
    continuation_hints = (
        "chopped", "diced", "minced", "sliced", "grated", "crushed",
        "melted", "softened", "room temperature", "sifted", "beaten",
        "fresh", "dried", "ground", "thinly", "finely", "roughly",
        "toasted", "split", "peeled", "deveined", "halved", "quartered",
        "shredded", "cubed", "julienned", "blanched", "roasted", "fried",
        "drained", "rinsed", "trimmed", "seeded", "cored", "pitted",
        "softened", "melted", "beaten", "whisked", "softened",
    )
    lowered = text.lower()
    return any(hint in lowered for hint in continuation_hints)


def _merge_ingredient_fragments(parts: list[str]) -> list[str]:
    """Merge column remnants and continuation fragments onto the previous ingredient."""
    merged: list[str] = []
    for part in parts:
        part = re.sub(r"\s+", " ", _strip_quotes(part)).strip()
        if not part:
            continue

        if _is_column_remnant(part):
            if merged:
                merged[-1] = f"{merged[-1]} ({part.rstrip('.')})"
            continue

        if merged and _looks_like_continuation(part):
            merged[-1] = f"{merged[-1]}, {part}"
            continue

        merged.append(part)

    return merged


def _split_consolidated_block(block: str) -> list[str]:
    if not block:
        return []

    # Prefer semicolon boundaries from consolidation
    if SEPARATOR.strip() in block or ";" in block:
        parts = [p.strip() for p in re.split(r"\s*;\s*", block) if p.strip()]
        return _merge_ingredient_fragments(parts)

    # Bracketed Python/JSON list string
    if block.startswith("[") and block.endswith("]"):
        literal_items = parse_python_style_list(block)
        if literal_items:
            return literal_items
        # Do not comma-split bracketed text — that breaks quoted list items.

    # Comma-separated plain text (e.g. Multi_Cuisine dataset — no bracket wrapper)
    if "," in block and not looks_like_python_list(block):
        parts = [p.strip() for p in block.split(",") if p.strip()]
        return _merge_ingredient_fragments([_strip_quotes(p) for p in parts])

    return _merge_ingredient_fragments([block])


def normalize_ingredient_list(raw: Any) -> list[str]:
    """
    Parse raw ingredients into a tight, one-item-per-line list for API responses.
    """
    if isinstance(raw, dict):
        return [json.dumps(raw, ensure_ascii=False)]

    literal_items = parse_python_style_list(raw)
    if literal_items:
        # Trust ast.literal_eval units — never comma-split inside quoted items
        parts = literal_items
    else:
        block = consolidate_raw_text_stream(raw)
        parts = _split_consolidated_block(block)

    seen: set[str] = set()
    result: list[str] = []
    for item in parts:
        item = re.sub(r"^\s*(?:[-*•]\s+|\d+[\).]\s*)", "", item).strip()
        item = re.sub(r"\s+", " ", item)
        if not item or len(item) < 2:
            continue
        key = item.lower()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


MAX_INSTRUCTION_WORDS = 22
MAX_INSTRUCTION_CHARS = 140
MIN_FRAGMENT_WORDS = 5
TARGET_COHERENT_STEPS = 6
MAX_COHERENT_STEP_WORDS = 55

_TEMPORAL_MARKER_RE = re.compile(
    r"\(\s*\d+\s*(?:min|mins|minute|minutes|hour|hours|hr|hrs)\s*\)",
    re.IGNORECASE,
)
_LEADING_STEP_NUM_RE = re.compile(r"^\s*\d+[\).]\s*", re.MULTILINE)
_STEP_PREFIX = re.compile(
    r"^\s*(?:\d+[\).]\s+|[-*•]\s+|step\s+\d+[:\.]?\s*)",
    re.IGNORECASE,
)


def _clean_instruction_step(text: str) -> str:
    text = _STEP_PREFIX.sub("", str(text)).strip()
    text = _TEMPORAL_MARKER_RE.sub("", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def sanitize_recipe_instructions(raw_text: Any) -> str:
    """
    Sanitization layer: strip erroneous temporal markers and newline noise,
    then stitch fragments into one unified instruction block.
    """
    if raw_text is None:
        return ""

    if isinstance(raw_text, list):
        parts = [str(item).strip() for item in raw_text if item is not None and str(item).strip()]
        text = "\n".join(parts)
    else:
        text = str(raw_text)

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _TEMPORAL_MARKER_RE.sub("", text)
    text = _LEADING_STEP_NUM_RE.sub("", text)

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return ""

    merged_lines: list[str] = []
    for line in lines:
        line = _clean_instruction_step(line)
        if not line:
            continue
        if (
            merged_lines
            and not re.search(r"[.!?]$", merged_lines[-1])
            and (line[0].islower() or len(line.split()) <= MIN_FRAGMENT_WORDS)
        ):
            merged_lines[-1] = f"{merged_lines[-1]} {line}"
        else:
            merged_lines.append(line)

    unified = " ".join(merged_lines)
    unified = re.sub(r"\s+", " ", unified).strip()
    unified = re.sub(r"\s+([,.!?;:])", r"\1", unified)
    unified = re.sub(r",([A-Za-z])", r", \1", unified)
    unified = re.sub(r"\.([A-Z])", r". \1", unified)
    unified = re.sub(r"!([A-Z])", r"! \1", unified)
    unified = re.sub(r"\?([A-Z])", r"? \1", unified)
    return unified.strip()


def _ensure_step_period(text: str) -> str:
    text = text.strip()
    if text and text[-1] not in ".!?":
        text = f"{text}."
    return text


_ABBREV_PROTECT = (
    "tsp.", "tbsp.", "oz.", "lb.", "lbs.", "ml.", "l.", "g.", "kg.", "hr.", "min.",
    "deg.", "no.", "dr.", "mr.", "mrs.", "vs.", "etc.", "e.g.", "i.e.",
)


def _split_instruction_sentences(text: str) -> list[str]:
    """Split on sentence boundaries without breaking quantities like '1/2 tsp.'"""
    protected = text
    placeholders: dict[str, str] = {}
    for index, abbrev in enumerate(_ABBREV_PROTECT):
        token = f"__ABBR{index}__"
        placeholders[token] = abbrev
        protected = re.sub(re.escape(abbrev), token, protected, flags=re.IGNORECASE)

    parts = re.split(r"(?<=[.!?])\s+", protected)
    sentences: list[str] = []
    for part in parts:
        restored = part
        for token, abbrev in placeholders.items():
            restored = restored.replace(token, abbrev)
        restored = restored.strip()
        if restored and len(restored) > 3:
            sentences.append(restored)
    return sentences


def _group_sentences_into_coherent_steps(unified: str) -> list[str]:
    """Group sanitized prose into ~5–6 logical cooking phases (not micro-fragments)."""
    unified = _clean_instruction_step(unified)
    if not unified:
        return []

    sentences = _split_instruction_sentences(unified)
    if not sentences:
        return [unified]

    if len(sentences) <= TARGET_COHERENT_STEPS:
        return [_ensure_step_period(s) for s in sentences]

def _group_sentences_into_coherent_steps(unified: str) -> list[str]:
    """Group sanitized prose into ~5–6 logical cooking phases (not micro-fragments)."""
    unified = _clean_instruction_step(unified)
    if not unified:
        return []

    sentences = _split_instruction_sentences(unified)
    if not sentences:
        return [unified]

    if len(sentences) <= TARGET_COHERENT_STEPS:
        return [_ensure_step_period(s) for s in sentences]

    steps: list[str] = []
    total = len(sentences)
    for index in range(TARGET_COHERENT_STEPS):
        start = (index * total) // TARGET_COHERENT_STEPS
        end = ((index + 1) * total) // TARGET_COHERENT_STEPS
        chunk = " ".join(sentences[start:end])
        if chunk:
            steps.append(_ensure_step_period(chunk))
    return steps or [_ensure_step_period(unified)]


def instructions_look_fragmented(steps: list[str]) -> bool:
    """True when steps look like a puzzle (newline/timing splits) rather than real phases."""
    if not steps:
        return False

    cleaned = [_clean_instruction_step(str(step)) for step in steps if str(step).strip()]
    if not cleaned:
        return False

    if len(cleaned) > 10:
        return True

    avg_words = sum(len(step.split()) for step in cleaned) / len(cleaned)
    if len(cleaned) > TARGET_COHERENT_STEPS and avg_words < 12:
        return True

    tiny = sum(1 for step in cleaned if len(step.split()) <= 3)
    if tiny >= max(2, len(cleaned) // 3):
        return True

    if any(_TEMPORAL_MARKER_RE.fullmatch(step.strip()) for step in cleaned):
        return True

    return False


def _merge_tiny_fragments(steps: list[str]) -> list[str]:
    """Attach very short tail fragments (e.g. 'Keep aside.') to the previous step."""
    if not steps:
        return []
    merged: list[str] = [steps[0]]
    for step in steps[1:]:
        if len(step.split()) < MIN_FRAGMENT_WORDS and merged:
            prev = merged[-1].rstrip(".!?")
            merged[-1] = f"{prev}. {step.lstrip('. ')}" if prev else step
        else:
            merged.append(step)
    return merged


def _split_long_clause(text: str) -> list[str]:
    """Split an oversized single sentence on natural cooking clause boundaries."""
    text = _clean_instruction_step(text)
    if not text:
        return []
    if len(text.split()) <= MAX_INSTRUCTION_WORDS and len(text) <= MAX_INSTRUCTION_CHARS:
        return [text]

    for pattern in (
        r"\s*;\s+",
        r"\s+and then\s+",
        r"\s+then\s+",
        r",\s+and\s+",
        r",\s+(?=(?:add|mix|stir|heat|cook|bake|simmer|boil|fry|saute|sauté|serve|garnish|remove|transfer|cover|reduce|whisk|blend|pour|season|taste|plate|preheat|combine|fold|drain|rinse|slice|chop|dice|mince|peel|marinate|roast|grill|steam|blend|set aside|keep aside|pressure cook)\b)",
    ):
        parts = re.split(pattern, text, flags=re.IGNORECASE)
        if len(parts) > 1:
            out: list[str] = []
            for part in parts:
                out.extend(_split_long_clause(part))
            return out

    words = text.split()
    chunks: list[str] = []
    for i in range(0, len(words), MAX_INSTRUCTION_WORDS):
        chunk = " ".join(words[i : i + MAX_INSTRUCTION_WORDS]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks or [text]


def _split_bulky_instruction(text: str) -> list[str]:
    """Break wall-of-text instructions into short, single-action steps."""
    text = _clean_instruction_step(text)
    if not text:
        return []

    # Fix missing spaces after punctuation glued to the next word/sentence.
    text = re.sub(r",([A-Za-z])", r", \1", text)
    text = re.sub(r"\.([A-Z])", r". \1", text)
    text = re.sub(r"!([A-Z])", r"! \1", text)
    text = re.sub(r"\?([A-Z])", r"? \1", text)

    numbered = re.split(r"(?<=\.)\s+(?=\d+[\).]\s+)", text)
    if len(numbered) > 1:
        expanded: list[str] = []
        for part in numbered:
            expanded.extend(_split_bulky_instruction(part))
        return expanded

    bullets = re.split(r"\s*(?:\*|•)\s+", text)
    if len(bullets) > 1:
        expanded = []
        for part in bullets:
            expanded.extend(_split_bulky_instruction(part))
        if len(expanded) > 1:
            return expanded

    sentences = re.split(r"(?<=[.!?])\s+", text)
    if len(sentences) > 1:
        steps: list[str] = []
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence:
                steps.extend(_split_long_clause(sentence))
        return _merge_tiny_fragments(steps)

    return _merge_tiny_fragments(_split_long_clause(text))


def _collect_instruction_chunks(raw: Any) -> list[str]:
    """Return unified instruction blocks — never split on bare newlines."""
    unified = sanitize_recipe_instructions(raw)
    if not unified:
        return []

    literal = parse_python_style_list(raw) if not isinstance(raw, list) else None
    if literal and len(literal) > 1:
        blocks = [sanitize_recipe_instructions(item) for item in literal]
        return [block for block in blocks if block]

    return [unified]


def normalize_instruction_list(raw: Any) -> list[str]:
    """Return ordered, coherent cooking steps — sanitized and logically grouped."""
    chunks = _collect_instruction_chunks(raw)
    steps: list[str] = []
    for chunk in chunks:
        steps.extend(_group_sentences_into_coherent_steps(chunk))

    seen: set[str] = set()
    ordered: list[str] = []
    for step in steps:
        step = _ensure_step_period(_clean_instruction_step(step))
        if len(step) < 4:
            continue
        key = step.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(step)
    return ordered


def normalize_recipe_payload(recipe: dict) -> dict:
    """Ensure recipe dict has consolidated ingredients/instructions before API output."""
    normalized = dict(recipe)
    normalized["ingredients"] = normalize_ingredient_list(normalized.get("ingredients", []))
    normalized["instructions"] = normalize_instruction_list(normalized.get("instructions", []))
    return normalized
