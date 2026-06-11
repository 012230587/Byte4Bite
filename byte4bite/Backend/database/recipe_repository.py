"""
Recipe persistence layer — all reads/writes to `asian_recipes` go through here.

Embeddings are stored as VARBINARY(3072) for MySQL 8.0 compatibility.
Cosine ranking is computed in Python (numpy) over keyword-filtered candidates.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import numpy as np

from .connection import get_connection
from services.text_consolidation import (
    normalize_ingredient_list,
    normalize_instruction_list,
    parse_python_style_list,
)

# Lazy import to avoid circular dependency with rag.embeddings at module load.
def _is_zero_embedding(blob: Optional[bytes]) -> bool:
    from rag.embeddings import is_zero_embedding
    return is_zero_embedding(blob)


def _parse_stored_json_field(value: Any) -> Any:
    """Load JSON columns from MySQL; fall back to ast.literal_eval for legacy Python lists."""
    if value is None:
        return []
    if isinstance(value, (list, dict)):
        return value
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        parsed = parse_python_style_list(value)
        return parsed if parsed is not None else value

EMBEDDING_DIMENSION = 768
EMBEDDING_BYTE_SIZE = EMBEDDING_DIMENSION * 4  # float32

# User bookmarks are stored in saved_recipes; copies with this source_file must not
# pollute ingredient search (only dataset CSV rows belong in the search corpus).
SEARCH_CORPUS_FILTER = "(source_file IS NULL OR source_file <> 'user_saved')"


def bytes_to_vector(data: bytes) -> np.ndarray:
    """Unpack float32 embedding bytes from MySQL VARBINARY column."""
    return np.frombuffer(data, dtype=np.float32)


def row_to_recipe(row: dict[str, Any]) -> dict[str, Any]:
    """Map a MySQL row dict into the FastAPI recipe response shape."""
    ingredients = row.get("ingredients") or []
    instructions = row.get("instructions") or []
    dietary_tags = row.get("dietary_tags") or []

    ingredients = _parse_stored_json_field(ingredients)
    instructions = _parse_stored_json_field(instructions)
    if isinstance(dietary_tags, str):
        try:
            dietary_tags = json.loads(dietary_tags)
        except json.JSONDecodeError:
            dietary_tags = parse_python_style_list(dietary_tags) or []

    return {
        "id": row.get("recipe_id"),
        "title": row.get("title", ""),
        "description": row.get("description") or "",
        "ingredients": normalize_ingredient_list(ingredients),
        "instructions": normalize_instruction_list(instructions),
        "prep_time": row.get("prep_time") or "30 mins",
        "difficulty": row.get("difficulty") or "Medium",
        "cuisine": row.get("cuisine"),
        "dietary_tags": dietary_tags,
        "metadata": {
            "recipe_id": row.get("recipe_id"),
            "cuisine": row.get("cuisine"),
            "source_file": row.get("source_file"),
        },
    }


class RecipeRepository:
    """CRUD + search operations on `asian_recipes`."""

    @staticmethod
    def list_ingested_source_files() -> set[str]:
        """Distinct CSV filenames already loaded into asian_recipes."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT source_file
                FROM asian_recipes
                WHERE source_file IS NOT NULL AND source_file <> ''
                """
            )
            rows = cursor.fetchall()
            cursor.close()
        return {row[0] for row in rows if row and row[0]}

    @staticmethod
    def count_by_source_file(source_file: str) -> int:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM asian_recipes WHERE source_file = %s",
                (source_file,),
            )
            row = cursor.fetchone()
            cursor.close()
        return int(row[0]) if row else 0

    @staticmethod
    def clear_all_corpus() -> dict[str, int]:
        """Delete every ingested recipe and all user bookmarks."""
        bookmarks = RecipeRepository.clear_all_saved_recipes()
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM asian_recipes WHERE recipe_id > 0")
            corpus = cursor.rowcount
            cursor.close()
        return {"saved_recipes_deleted": bookmarks, "corpus_deleted": int(corpus)}

    @staticmethod
    def clear_all_saved_recipes() -> int:
        """Remove every row from saved_recipes (user bookmarks)."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM saved_recipes WHERE saved_id > 0")
            deleted = cursor.rowcount
            cursor.close()
        return int(deleted)

    @staticmethod
    def delete_user_saved_corpus() -> int:
        """Remove generated/saved copies from asian_recipes (not dataset CSV rows)."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM asian_recipes
                WHERE source_file = 'user_saved' AND recipe_id > 0
                """
            )
            deleted = cursor.rowcount
            cursor.close()
        return int(deleted)

    @staticmethod
    def delete_by_source_file(source_file: str) -> int:
        """Drop all corpus rows from one dataset CSV before a fresh re-ingest."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM asian_recipes
                WHERE source_file = %s AND recipe_id > 0
                """,
                (source_file,),
            )
            deleted = cursor.rowcount
            cursor.close()
        return int(deleted)

    @staticmethod
    def title_exists(title: str) -> bool:
        """Used by ingest.py to skip duplicates before calling the embedding API."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM asian_recipes WHERE title = %s LIMIT 1",
                (title.strip(),),
            )
            exists = cursor.fetchone() is not None
            cursor.close()
            return exists

    @staticmethod
    def insert_recipe(
        title: str,
        description: str,
        ingredients: list[str],
        instructions: list[str],
        prep_time: str,
        difficulty: str,
        cuisine: Optional[str],
        dietary_tags: list[str],
        source_file: str,
        embedding_bytes: bytes,
    ) -> int:
        """
        Insert a new recipe with its binary embedding (768 float32 → 3072 bytes).
        """
        if len(embedding_bytes) != EMBEDDING_BYTE_SIZE:
            raise ValueError(
                f"embedding_bytes must be {EMBEDDING_BYTE_SIZE} bytes, got {len(embedding_bytes)}"
            )

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO asian_recipes (
                    title, description, ingredients, instructions,
                    prep_time, difficulty, cuisine, dietary_tags,
                    source_file, embedding
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s
                )
                """,
                (
                    title.strip(),
                    description,
                    json.dumps(ingredients, ensure_ascii=False),
                    json.dumps(instructions, ensure_ascii=False),
                    prep_time,
                    difficulty,
                    cuisine,
                    json.dumps(dietary_tags, ensure_ascii=False),
                    source_file,
                    embedding_bytes,
                ),
            )
            recipe_id = cursor.lastrowid
            cursor.close()
            return int(recipe_id)

    @staticmethod
    def fetch_all(limit: int = 500) -> list[dict[str, Any]]:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT recipe_id, title, description, ingredients, instructions,
                       prep_time, difficulty, cuisine, dietary_tags, source_file
                FROM asian_recipes
                ORDER BY recipe_id
                LIMIT %s
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            cursor.close()
            return [row_to_recipe(r) for r in rows]

    @staticmethod
    def count() -> int:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM asian_recipes")
            (count,) = cursor.fetchone()
            cursor.close()
            return int(count)

    @staticmethod
    def keyword_search(query: str, limit: int = 200) -> list[dict[str, Any]]:
        """LIKE search across title, description, ingredients JSON, and instructions."""
        import re

        terms = [t.strip() for t in re.split(r"[,;]+", query) if t.strip()]
        if not terms:
            terms = [query.strip()]

        clauses = []
        params: list[Any] = []
        for term in terms:
            pattern = f"%{term}%"
            clauses.append(
                "(title LIKE %s OR description LIKE %s "
                "OR CAST(ingredients AS CHAR) LIKE %s "
                "OR CAST(instructions AS CHAR) LIKE %s)"
            )
            params.extend([pattern, pattern, pattern, pattern])

        where_sql = " OR ".join(clauses)
        sql = f"""
            SELECT recipe_id, title, description, ingredients, instructions,
                   prep_time, difficulty, cuisine, dietary_tags, source_file
            FROM asian_recipes
            WHERE ({where_sql}) AND {SEARCH_CORPUS_FILTER}
            LIMIT %s
        """
        params.append(limit)

        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            cursor.close()
            return [row_to_recipe(r) for r in rows]

    @staticmethod
    def fetch_search_pool(limit: int = 15000) -> list[dict[str, Any]]:
        """Load recipes for in-Python ranking when broad search is needed."""
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                f"""
                SELECT recipe_id, title, description, ingredients, instructions,
                       prep_time, difficulty, cuisine, dietary_tags, source_file
                FROM asian_recipes
                WHERE {SEARCH_CORPUS_FILTER}
                ORDER BY recipe_id
                LIMIT %s
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            cursor.close()
            return [row_to_recipe(r) for r in rows]

    @staticmethod
    def vector_search_scored(
        query_vector: np.ndarray,
        limit: int = 10,
        candidate_ids: Optional[list[int]] = None,
    ) -> list[tuple[float, dict[str, Any]]]:
        """
        Cosine similarity search over VARBINARY embeddings (MySQL 8.0 compatible).
        Returns (similarity_score, recipe_dict) pairs, highest first.
        """
        if query_vector.shape[0] != EMBEDDING_DIMENSION:
            return []

        id_filter = ""
        params: list[Any] = []

        if candidate_ids:
            placeholders = ",".join(["%s"] * len(candidate_ids))
            id_filter = f"AND recipe_id IN ({placeholders})"
            params = list(candidate_ids)

        sql = f"""
            SELECT recipe_id, title, description, ingredients, instructions,
                   prep_time, difficulty, cuisine, dietary_tags, source_file,
                   embedding
            FROM asian_recipes
            WHERE embedding IS NOT NULL
            AND {SEARCH_CORPUS_FILTER}
            {id_filter}
        """

        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            cursor.close()

        if not rows:
            return []

        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            blob = row.get("embedding")
            if _is_zero_embedding(blob):
                continue
            vec = bytes_to_vector(blob)
            score = float(np.dot(query_vector, vec))
            recipe = row_to_recipe(row)
            recipe["similarity_score"] = round(score, 4)
            recipe["search_mode"] = "vector"
            scored.append((score, recipe))

        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[:limit]

    @staticmethod
    def vector_search(
        query_vector: np.ndarray,
        limit: int = 10,
        candidate_ids: Optional[list[int]] = None,
    ) -> list[dict[str, Any]]:
        """Cosine similarity search — returns recipes ranked by similarity."""
        scored = RecipeRepository.vector_search_scored(
            query_vector, limit=limit, candidate_ids=candidate_ids
        )
        return [recipe for _, recipe in scored]

    @staticmethod
    def log_search(
        user_id: Optional[int],
        query_text: str,
        search_mode: str = "browse",
    ) -> None:
        mode = (search_mode or "browse").strip().lower()[:32]
        with get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO search_history (user_id, query_text, search_mode)
                    VALUES (%s, %s, %s)
                    """,
                    (user_id, query_text[:500], mode),
                )
            except Exception:
                cursor.execute(
                    "INSERT INTO search_history (user_id, query_text) VALUES (%s, %s)",
                    (user_id, query_text[:500]),
                )
            cursor.close()

    @staticmethod
    def fetch_embedding_backfill_batch(
        after_recipe_id: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch corpus rows for embedding backfill (raw JSON fields preserved)."""
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                f"""
                SELECT recipe_id, title, description, ingredients, instructions,
                       cuisine, embedding
                FROM asian_recipes
                WHERE {SEARCH_CORPUS_FILTER}
                  AND recipe_id > %s
                ORDER BY recipe_id
                LIMIT %s
                """,
                (after_recipe_id, limit),
            )
            rows = cursor.fetchall()
            cursor.close()
        return list(rows)

    @staticmethod
    def update_embedding(recipe_id: int, embedding_bytes: bytes) -> None:
        """Persist a new embedding blob for one recipe."""
        if len(embedding_bytes) != EMBEDDING_BYTE_SIZE:
            raise ValueError(
                f"embedding_bytes must be {EMBEDDING_BYTE_SIZE} bytes, got {len(embedding_bytes)}"
            )
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE asian_recipes
                SET embedding = %s, updated_at = CURRENT_TIMESTAMP
                WHERE recipe_id = %s
                """,
                (embedding_bytes, recipe_id),
            )
            cursor.close()

    @staticmethod
    def count_embedding_stats() -> dict[str, int]:
        """Corpus embedding health for startup logs and backfill progress."""
        stats = {"total_corpus": 0, "null_embeddings": 0, "valid_embeddings": 0, "needs_backfill": 0}
        batch_size = 500
        after_id = 0

        while True:
            rows = RecipeRepository.fetch_embedding_backfill_batch(
                after_recipe_id=after_id,
                limit=batch_size,
            )
            if not rows:
                break

            for row in rows:
                stats["total_corpus"] += 1
                blob = row.get("embedding")
                if blob is None:
                    stats["null_embeddings"] += 1
                    stats["needs_backfill"] += 1
                elif _is_zero_embedding(blob):
                    stats["needs_backfill"] += 1
                else:
                    stats["valid_embeddings"] += 1

            after_id = int(rows[-1]["recipe_id"])

        return stats
