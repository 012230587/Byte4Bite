#!/usr/bin/env python3
"""
Backfill real embeddings for corpus rows that have NULL or zero placeholders.

Run from Backend/:
  python -m rag.backfill_embeddings
  python -m rag.backfill_embeddings --limit 50
  python -m rag.backfill_embeddings --dry-run
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(BACKEND_DIR / ".env")

from database.recipe_repository import RecipeRepository
from rag.embeddings import (
    EMBEDDING_MODEL,
    build_recipe_embed_document_from_row,
    embed_text,
    is_zero_embedding,
    vector_to_bytes,
)


def _safe_console(text: str) -> str:
    return str(text).encode("ascii", errors="replace").decode("ascii")


def backfill_embeddings(
    *,
    batch_size: int = 50,
    sleep_seconds: float = 0.05,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    stats = {
        "scanned": 0,
        "updated": 0,
        "skipped_valid": 0,
        "errors": 0,
    }

    after_id = 0
    while True:
        if limit is not None and stats["updated"] >= limit:
            break

        rows = RecipeRepository.fetch_embedding_backfill_batch(
            after_recipe_id=after_id,
            limit=batch_size,
        )
        if not rows:
            break

        for row in rows:
            if limit is not None and stats["updated"] >= limit:
                break

            stats["scanned"] += 1
            recipe_id = int(row["recipe_id"])
            after_id = recipe_id

            if not is_zero_embedding(row.get("embedding")):
                stats["skipped_valid"] += 1
                continue

            title = _safe_console(str(row.get("title", ""))[:70])
            try:
                document = build_recipe_embed_document_from_row(row)
                if dry_run:
                    print(f"  [dry-run] Would embed #{recipe_id}: {title}")
                    stats["updated"] += 1
                    continue

                vector = embed_text(document)
                RecipeRepository.update_embedding(recipe_id, vector_to_bytes(vector))
                stats["updated"] += 1
                if stats["updated"] % 25 == 0 or stats["updated"] <= 3:
                    print(f"  [ok] Embedded #{recipe_id}: {title}")

                if sleep_seconds:
                    time.sleep(sleep_seconds)
            except Exception as exc:
                stats["errors"] += 1
                print(f"  [err] #{recipe_id} {title}: {exc}")

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill recipe embeddings in MySQL")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--sleep", type=float, default=0.05)
    parser.add_argument("--limit", type=int, default=None, help="Max recipes to (re)embed")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    before = RecipeRepository.count_embedding_stats()
    print("Byte4Bite Embedding Backfill")
    print(f"  Model           : {EMBEDDING_MODEL}")
    print(f"  Before          : valid={before['valid_embeddings']}, needs_backfill={before['needs_backfill']}")
    print(f"  Dry run         : {args.dry_run}")

    stats = backfill_embeddings(
        batch_size=args.batch_size,
        sleep_seconds=args.sleep,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    after = RecipeRepository.count_embedding_stats() if not args.dry_run else before
    print("\n-- Summary --")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    if not args.dry_run:
        print(
            f"  After: valid={after['valid_embeddings']}, "
            f"needs_backfill={after['needs_backfill']}, corpus={after['total_corpus']}"
        )


if __name__ == "__main__":
    main()
