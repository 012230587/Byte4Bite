"""
User accounts, profiles, and saved recipe bookmarks (MySQL).
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .connection import get_connection
from .recipe_repository import RecipeRepository, row_to_recipe


class UserRepository:
    @staticmethod
    def email_exists(email: str) -> bool:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM users WHERE email = %s LIMIT 1", (email.lower().strip(),))
            found = cur.fetchone() is not None
            cur.close()
            return found

    @staticmethod
    def create_user(email: str, password_hash: str) -> int:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (email, password_hash) VALUES (%s, %s)",
                (email.lower().strip(), password_hash),
            )
            user_id = int(cur.lastrowid)
            cur.execute(
                "INSERT INTO user_profiles (user_id) VALUES (%s)",
                (user_id,),
            )
            cur.close()
            return user_id

    @staticmethod
    def get_user_by_email(email: str) -> Optional[dict[str, Any]]:
        with get_connection() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT user_id, email, password_hash, created_at FROM users WHERE email = %s",
                (email.lower().strip(),),
            )
            row = cur.fetchone()
            cur.close()
            return row

    @staticmethod
    def get_user_by_id(user_id: int) -> Optional[dict[str, Any]]:
        with get_connection() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT user_id, email, created_at FROM users WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            cur.close()
            return row

    @staticmethod
    def get_profile(user_id: int) -> Optional[dict[str, Any]]:
        with get_connection() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT u.user_id, u.email, u.created_at,
                       p.dietary_restriction, p.allergies, p.health_goals, p.updated_at
                FROM users u
                LEFT JOIN user_profiles p ON p.user_id = u.user_id
                WHERE u.user_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
            cur.close()
            if not row:
                return None
            for field in ("allergies", "health_goals"):
                if isinstance(row.get(field), str):
                    row[field] = json.loads(row[field])
            return row

    @staticmethod
    def update_profile(
        user_id: int,
        dietary_restriction: Optional[str] = None,
        allergies: Optional[list] = None,
        health_goals: Optional[list] = None,
    ) -> None:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE user_profiles
                SET dietary_restriction = %s,
                    allergies = %s,
                    health_goals = %s
                WHERE user_id = %s
                """,
                (
                    dietary_restriction,
                    json.dumps(allergies or []),
                    json.dumps(health_goals or []),
                    user_id,
                ),
            )
            cur.close()

    @staticmethod
    def _upsert_recipe_for_save(recipe: dict[str, Any]) -> int:
        """Ensure recipe exists in asian_recipes; return recipe_id."""
        title = (recipe.get("title") or "").strip()
        if not title:
            raise ValueError("Recipe title is required")

        if RecipeRepository.title_exists(title):
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT recipe_id FROM asian_recipes WHERE title = %s", (title,))
                row = cur.fetchone()
                cur.close()
                if row:
                    return int(row[0])

        return RecipeRepository.insert_recipe(
            title=title,
            description=recipe.get("description", ""),
            ingredients=recipe.get("ingredients", []),
            instructions=recipe.get("instructions", []),
            prep_time=recipe.get("prep_time", "30 mins"),
            difficulty=recipe.get("difficulty", "Medium"),
            cuisine=recipe.get("cuisine"),
            dietary_tags=recipe.get("dietary_tags", []),
            source_file="user_saved",
            embedding_bytes=b"\x00" * 3072,
        )

    @staticmethod
    def save_recipe_for_user(user_id: int, recipe: dict[str, Any], notes: str = "") -> dict[str, Any]:
        recipe_id = UserRepository._upsert_recipe_for_save(recipe)
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO saved_recipes (user_id, recipe_id, notes)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE notes = VALUES(notes), saved_at = CURRENT_TIMESTAMP
                """,
                (user_id, recipe_id, notes),
            )
            cur.close()

        with get_connection() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT r.recipe_id, r.title, r.description, r.ingredients, r.instructions,
                       r.prep_time, r.difficulty, r.cuisine, r.dietary_tags, r.source_file,
                       s.saved_at, s.notes
                FROM saved_recipes s
                JOIN asian_recipes r ON r.recipe_id = s.recipe_id
                WHERE s.user_id = %s AND s.recipe_id = %s
                """,
                (user_id, recipe_id),
            )
            row = cur.fetchone()
            cur.close()

        result = row_to_recipe(row) if row else recipe
        result["saved_at"] = str(row.get("saved_at")) if row else None
        result["notes"] = row.get("notes") if row else notes
        return result

    @staticmethod
    def list_saved_recipes(user_id: int) -> list[dict[str, Any]]:
        with get_connection() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT r.recipe_id, r.title, r.description, r.ingredients, r.instructions,
                       r.prep_time, r.difficulty, r.cuisine, r.dietary_tags, r.source_file,
                       s.saved_at, s.notes
                FROM saved_recipes s
                JOIN asian_recipes r ON r.recipe_id = s.recipe_id
                WHERE s.user_id = %s
                ORDER BY s.saved_at DESC
                """,
                (user_id,),
            )
            rows = cur.fetchall()
            cur.close()

        results = []
        for row in rows:
            item = row_to_recipe(row)
            item["saved_at"] = str(row.get("saved_at"))
            item["notes"] = row.get("notes")
            results.append(item)
        return results
