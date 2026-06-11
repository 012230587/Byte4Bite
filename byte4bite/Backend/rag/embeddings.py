"""
Shared embedding utilities for ingest, backfill, and retrieval.

MySQL 8.0 stores vectors as VARBINARY(3072) = 768 float32 values.
Cosine similarity is computed in Python (see recipe_repository.vector_search).

Model: gemini-embedding-001 with output_dimensionality=768 (Google GenAI SDK).
"""

from __future__ import annotations

import os
from typing import Any, Optional

import numpy as np
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

from database.recipe_repository import EMBEDDING_BYTE_SIZE, EMBEDDING_DIMENSION

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001").strip()
API_KEY = os.getenv("GEMINI_API_KEY")
_client = genai.Client(api_key=API_KEY) if (genai is not None and API_KEY) else None


def should_embed_on_ingest() -> bool:
    """When true, ingest/sync writes real embeddings instead of zero placeholders."""
    return os.getenv("EMBED_ON_INGEST", "true").lower() in {"1", "true", "yes"}


def resolve_no_embed(explicit: Optional[bool] = None) -> bool:
    """Resolve --no-embed CLI flag vs EMBED_ON_INGEST env default."""
    if explicit is not None:
        return explicit
    return not should_embed_on_ingest()


def build_recipe_embed_document(
    *,
    title: str,
    description: str = "",
    ingredients: list[str] | None = None,
    instructions: list[str] | None = None,
    cuisine: Optional[str] = None,
) -> str:
    """
    Rich semantic document for recipe embedding (Phase A).
    Clusters soups, gravies, broths, and techniques beyond exact keywords.
    """
    title = (title or "").strip()
    description = (description or "").strip()
    cuisine = (cuisine or "").strip()
    ingredients = [str(i).strip() for i in (ingredients or []) if str(i).strip()]
    instructions = [str(s).strip() for s in (instructions or []) if str(s).strip()]

    method_hint = " ".join(instructions[:2])[:400]

    parts = [f"Title: {title}"]
    if cuisine:
        parts.append(f"Cuisine: {cuisine}")
    if description:
        parts.append(f"Description: {description}")
    if ingredients:
        parts.append(f"Ingredients: {', '.join(ingredients[:40])}")
    if method_hint:
        parts.append(f"Method: {method_hint}")
    return "\n".join(parts)


def build_recipe_embed_document_from_row(row: dict[str, Any]) -> str:
    """Build embed text from a repository/backfill row dict."""
    import json

    ingredients = row.get("ingredients") or []
    instructions = row.get("instructions") or []
    if isinstance(ingredients, str):
        try:
            ingredients = json.loads(ingredients)
        except json.JSONDecodeError:
            ingredients = [ingredients]
    if isinstance(instructions, str):
        try:
            instructions = json.loads(instructions)
        except json.JSONDecodeError:
            instructions = [instructions]

    return build_recipe_embed_document(
        title=str(row.get("title", "")),
        description=str(row.get("description") or ""),
        ingredients=list(ingredients) if isinstance(ingredients, list) else [],
        instructions=list(instructions) if isinstance(instructions, list) else [],
        cuisine=row.get("cuisine"),
    )


def is_zero_embedding(blob: Optional[bytes]) -> bool:
    """True when embedding is missing or a zero placeholder from --no-embed ingest."""
    if not blob or len(blob) != EMBEDDING_BYTE_SIZE:
        return True
    vec = np.frombuffer(blob, dtype=np.float32)
    return float(np.linalg.norm(vec)) < 1e-6


def zero_embedding_bytes() -> bytes:
    return np.zeros(EMBEDDING_DIMENSION, dtype=np.float32).tobytes()


def vector_to_bytes(vector: np.ndarray) -> bytes:
    return np.array(vector, dtype=np.float32).tobytes()


def embed_text(text: str) -> np.ndarray:
    """
    Embed arbitrary text with gemini-embedding-001 (768-dim, L2-normalized).
    Used for both corpus documents and user queries.
    """
    if _client is None:
        raise RuntimeError("GEMINI_API_KEY missing or google-genai not installed.")

    stripped = (text or "").strip()
    if not stripped:
        raise ValueError("Cannot embed empty text")

    config = None
    if types is not None:
        config = types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSION)

    response = _client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=stripped,
        config=config,
    )
    vec = np.array(response.embeddings[0].values, dtype=np.float32)

    if vec.shape[0] != EMBEDDING_DIMENSION:
        raise ValueError(
            f"Expected {EMBEDDING_DIMENSION}-dim embedding, got {vec.shape[0]}"
        )

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


def embed_recipe(
    *,
    title: str,
    description: str = "",
    ingredients: list[str] | None = None,
    instructions: list[str] | None = None,
    cuisine: Optional[str] = None,
) -> np.ndarray:
    """Embed a recipe using the shared rich document builder."""
    document = build_recipe_embed_document(
        title=title,
        description=description,
        ingredients=ingredients,
        instructions=instructions,
        cuisine=cuisine,
    )
    return embed_text(document)
