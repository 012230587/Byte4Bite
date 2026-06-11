#!/usr/bin/env python3
"""
Byte4Bite CSV → MySQL ingestion pipeline.

Data flow:
  datasets/*.csv  →  csv_utils (parse rows)
                 →  RecipeRepository.title_exists() (dedupe by UNIQUE title)
                 →  Google GenAI text-embedding-004 (title + ingredients)
                 →  asian_recipes table (text + VECTOR embedding)

Run from Backend/:
  python -m rag.ingest
  python -m rag.ingest --dry-run
  python -m rag.ingest --limit 50
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
from dotenv import load_dotenv

# Ensure Backend/ is on sys.path when executed as a script
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(BACKEND_DIR / ".env")

try:
    from google import genai
except ImportError:
    genai = None

import os

from database.recipe_repository import RecipeRepository, EMBEDDING_DIMENSION
from rag.csv_utils import DATASETS_DIR, iter_recipes_from_dataset, list_dataset_files
from services.text_consolidation import normalize_instruction_list, sanitize_recipe_instructions

EMBEDDING_MODEL = "text-embedding-004"
API_KEY = os.getenv("GEMINI_API_KEY")
_client = genai.Client(api_key=API_KEY) if (genai and API_KEY) else None


def _embed_recipe_text(title: str, ingredients: list[str]) -> np.ndarray:
    """
    Call Gemini text-embedding-004 on title + ingredients.
    Returns a normalized float32 vector of length 768.
    """
    if _client is None:
        raise RuntimeError("GEMINI_API_KEY missing or google-genai not installed.")

    text = f"{title}. Ingredients: {', '.join(ingredients)}"
    response = _client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
    )
    values = response.embeddings[0].values
    vec = np.array(values, dtype=np.float32)

    if vec.shape[0] != EMBEDDING_DIMENSION:
        raise ValueError(
            f"Expected {EMBEDDING_DIMENSION}-dim embedding, got {vec.shape[0]}"
        )

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


def _vector_to_bytes(vector: np.ndarray) -> bytes:
    """Pack float32 embedding as binary blob (768 * 4 = 3072 bytes)."""
    return np.array(vector, dtype=np.float32).tobytes()


def _zero_embedding_bytes() -> bytes:
    return np.zeros(EMBEDDING_DIMENSION, dtype=np.float32).tobytes()


def _safe_console(text: str) -> str:
    return str(text).encode("ascii", errors="replace").decode("ascii")


def list_dataset_csv_files() -> list[Path]:
    """Backward-compatible alias — includes CSV and Excel datasets."""
    return list_dataset_files()


def list_pending_dataset_files() -> list[Path]:
    """CSV files in datasets/ not yet recorded in MySQL (by source_file)."""
    all_files = list_dataset_csv_files()
    if not all_files:
        return []

    ingested = RecipeRepository.list_ingested_source_files()
    pending = [path for path in all_files if path.name not in ingested]

    # After a full corpus wipe, source_file metadata is gone — re-ingest all CSVs.
    if not pending and RecipeRepository.count() == 0:
        return all_files

    return pending


def clear_saved_recipe_data() -> dict[str, int]:
    """
    Remove all user bookmarks and user_saved search copies.
    Dataset CSV recipes in asian_recipes are kept unless you run --refresh.
    """
    from services.memory_service import clear_all_recipe_memory

    return clear_all_recipe_memory()


def refresh_datasets_from_folder(
    *,
    no_embed: bool = True,
    dry_run: bool = False,
    sleep_seconds: float = 0.0,
    clear_saved: bool = True,
) -> dict[str, int]:
    """
    Full dataset reload from datasets/*.csv:
      1. Clear saved_recipes + user_saved corpus (optional)
      2. For each CSV: delete old rows with that source_file
      3. Re-parse and insert all recipes from the file
    """
    totals = {
        "files_refreshed": 0,
        "removed_old_rows": 0,
        "scanned": 0,
        "skipped_existing": 0,
        "skipped_invalid": 0,
        "inserted": 0,
        "errors": 0,
        "saved_recipes_deleted": 0,
        "user_saved_deleted": 0,
    }

    csv_files = list_dataset_csv_files()
    if not csv_files:
        print(f"No CSV files found in {DATASETS_DIR}")
        return totals

    if clear_saved and not dry_run:
        cleared = clear_saved_recipe_data()
        totals["saved_recipes_deleted"] = cleared["saved_recipes_deleted"]
        totals["user_saved_deleted"] = cleared["user_saved_deleted"]
    elif clear_saved:
        print("DEBUG: [dry-run] Would clear saved_recipes and user_saved corpus")

    for csv_path in csv_files:
        print(f"\n-- Refreshing: {csv_path.name}")
        if not dry_run:
            removed = RecipeRepository.delete_by_source_file(csv_path.name)
            totals["removed_old_rows"] += removed
            print(f"  Removed {removed} existing row(s) for this source_file")

        file_stats = ingest_csv_files(
            csv_files=[csv_path],
            dry_run=dry_run,
            no_embed=no_embed,
            sleep_seconds=sleep_seconds if not no_embed else 0.0,
        )
        totals["files_refreshed"] += 1
        for key in ("scanned", "skipped_existing", "skipped_invalid", "inserted", "errors"):
            totals[key] += file_stats.get(key, 0)

    if not dry_run:
        try:
            from services import recipe_service
            recipe_service.invalidate_recipe_cache()
        except Exception:
            pass

    print(
        f"DEBUG: Dataset refresh complete — files={totals['files_refreshed']}, "
        f"inserted={totals['inserted']}, removed_old={totals['removed_old_rows']}, "
        f"errors={totals['errors']}, total_in_db={RecipeRepository.count() if not dry_run else 'n/a'}"
    )
    return totals


def sync_new_datasets(
    *,
    no_embed: bool = True,
    dry_run: bool = False,
    sleep_seconds: float = 0.0,
) -> dict[str, int]:
    """
    Auto-ingest newly added dataset CSVs into MySQL.

    Only processes files whose filename is not yet present in asian_recipes.source_file.
    Existing titles are still skipped via title_exists() deduplication.
    """
    pending = list_pending_dataset_files()
    if not pending:
        print("DEBUG: All dataset CSV files are already synced to MySQL")
        return {
            "files_synced": 0,
            "scanned": 0,
            "skipped_existing": 0,
            "skipped_invalid": 0,
            "inserted": 0,
            "errors": 0,
        }

    names = [path.name for path in pending]
    print(f"DEBUG: Syncing {len(pending)} new dataset file(s): {names}")
    stats = ingest_csv_files(
        csv_files=pending,
        dry_run=dry_run,
        no_embed=no_embed,
        sleep_seconds=sleep_seconds if not no_embed else 0.0,
    )
    stats["files_synced"] = len(pending)
    print(
        f"DEBUG: Dataset sync complete — inserted={stats['inserted']}, "
        f"skipped_existing={stats['skipped_existing']}, errors={stats['errors']}, "
        f"total_in_db={RecipeRepository.count() if not dry_run else 'n/a'}"
    )
    return stats


def ingest_csv_files(
    dry_run: bool = False,
    limit: Optional[int] = None,
    sleep_seconds: float = 0.05,
    no_embed: bool = False,
    csv_files: Optional[list[Path]] = None,
) -> dict[str, int]:
    """
    Scan datasets/ CSV files, dedupe by title in MySQL, embed new rows, insert.
    Pass csv_files to ingest a subset (e.g. only newly added datasets).
    """
    stats = {"scanned": 0, "skipped_existing": 0, "skipped_invalid": 0, "inserted": 0, "errors": 0}

    csv_files = sorted(csv_files) if csv_files else list_dataset_csv_files()
    if not csv_files:
        print(f"No dataset files found in {DATASETS_DIR} (expected *.csv or *.xlsx)")
        return stats

    print(f"Found {len(csv_files)} dataset file(s) to process")

    for csv_path in csv_files:
        print(f"\n-- Processing: {csv_path.name}")
        recipes = iter_recipes_from_dataset(csv_path)

        for recipe in recipes:
            if limit is not None and stats["inserted"] >= limit:
                print(f"Reached --limit {limit}, stopping.")
                return stats

            stats["scanned"] += 1
            title = recipe["title"]

            try:
                if RecipeRepository.title_exists(title):
                    stats["skipped_existing"] += 1
                    continue

                if dry_run:
                    print(f"  [dry-run] Would insert: {_safe_console(title[:60])}")
                    stats["inserted"] += 1
                    continue

                if no_embed:
                    embedding_bytes = _zero_embedding_bytes()
                else:
                    vector = _embed_recipe_text(title, recipe["ingredients"])
                    embedding_bytes = _vector_to_bytes(vector)

                # Sanitization layer: strip (X mins) noise and stitch newline fragments before DB write.
                recipe["instructions"] = normalize_instruction_list(
                    sanitize_recipe_instructions(recipe.get("instructions", []))
                )

                recipe_id = RecipeRepository.insert_recipe(
                    title=title,
                    description=recipe["description"],
                    ingredients=recipe["ingredients"],
                    instructions=recipe["instructions"],
                    prep_time=recipe["prep_time"],
                    difficulty=recipe["difficulty"],
                    cuisine=recipe.get("cuisine"),
                    dietary_tags=recipe.get("dietary_tags", []),
                    source_file=recipe["source_file"],
                    embedding_bytes=embedding_bytes,
                )
                stats["inserted"] += 1
                print(f"  [ok] Inserted #{recipe_id}: {_safe_console(title[:70])}")

                if sleep_seconds:
                    time.sleep(sleep_seconds)

            except Exception as exc:
                stats["errors"] += 1
                print(f"  [err] Error on '{_safe_console(title[:50])}': {exc}")

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest CSV recipes into MySQL with embeddings")
    parser.add_argument("--dry-run", action="store_true", help="Parse and dedupe only; no API/DB writes")
    parser.add_argument("--limit", type=int, default=None, help="Max new recipes to insert")
    parser.add_argument("--sleep", type=float, default=0.05, help="Seconds between embedding API calls")
    parser.add_argument(
        "--no-embed",
        action="store_true",
        help="Skip Gemini embeddings (fast bulk load; keyword search still works)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process every CSV in datasets/ (default: only files not yet in MySQL)",
    )
    parser.add_argument(
        "--sync-new",
        action="store_true",
        help="Only ingest CSV files not yet recorded in MySQL (same as default without --all)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Clear saved recipes, re-read every datasets/*.csv, and reload MySQL corpus",
    )
    parser.add_argument(
        "--clear-saved-only",
        action="store_true",
        help="Only remove saved_recipes, user_saved corpus, and memory_store.json",
    )
    parser.add_argument(
        "--clear-memory",
        action="store_true",
        help="Alias for --clear-saved-only (wipes all recipe memory, keeps dataset corpus)",
    )
    args = parser.parse_args()

    print("Byte4Bite Ingestion Pipeline")
    print(f"  Embedding model : {EMBEDDING_MODEL if not args.no_embed else 'skipped'}")
    print(f"  Vector dimension: {EMBEDDING_DIMENSION}")
    print(f"  Dry run         : {args.dry_run}")
    print(f"  No embed        : {args.no_embed}")

    if args.clear_saved_only or args.clear_memory:
        stats = clear_saved_recipe_data() if not args.dry_run else {
            "saved_recipes_deleted": 0,
            "user_saved_deleted": 0,
            "memory_json_cleared": 0,
            "fine_tuning_removed": 0,
        }
        if args.dry_run:
            print("DEBUG: [dry-run] Would clear all recipe memory (JSON + MySQL bookmarks)")
    elif args.refresh:
        stats = refresh_datasets_from_folder(
            no_embed=args.no_embed,
            dry_run=args.dry_run,
            sleep_seconds=args.sleep,
            clear_saved=True,
        )
    elif args.all:
        stats = ingest_csv_files(
            dry_run=args.dry_run,
            limit=args.limit,
            sleep_seconds=args.sleep,
            no_embed=args.no_embed,
        )
    else:
        stats = sync_new_datasets(
            no_embed=args.no_embed,
            dry_run=args.dry_run,
            sleep_seconds=args.sleep,
        )
        if args.limit is not None:
            print("Note: --limit applies only with --all; sync-new ingests full pending files")

    print("\n-- Summary --")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    print(f"  Total in DB: {RecipeRepository.count() if not args.dry_run else 'n/a (dry-run)'}")


if __name__ == "__main__":
    main()
