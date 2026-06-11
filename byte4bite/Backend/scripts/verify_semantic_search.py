#!/usr/bin/env python3
"""
Phase A gate: probe semantic retrieval for integration plan acceptance queries.

Run from Backend/:
  python scripts/verify_semantic_search.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR / ".env")

from database.recipe_repository import RecipeRepository
from rag import retriever

PROBE_QUERIES = [
    "boiled chicken",
    "sauce for soup",
    "chicken gravy",
]

SOUP_BROTH_HINTS = (
    "soup", "broth", "stock", "poach", "simmer", "stew", "gravy", "consommé", "consomme", "bisque"
)


def _title_matches_intent(title: str, query: str) -> bool:
    lowered = title.lower()
    query_tokens = [t for t in query.lower().split() if len(t) > 2]
    if any(token in lowered for token in query_tokens):
        return True
    return any(hint in lowered for hint in SOUP_BROTH_HINTS)


def run_probes(top_k: int = 5) -> bool:
    stats = RecipeRepository.count_embedding_stats()
    print("Embedding health:", stats)
    if stats["valid_embeddings"] == 0:
        print("FAIL: No valid embeddings — run: python -m rag.backfill_embeddings")
        return False

    passed = 0
    for query in PROBE_QUERIES:
        print(f"\n=== Query: {query!r} ===")
        results = retriever.find_best_recipes(query, top_k=top_k)
        if not results:
            print("  FAIL: no results")
            continue

        for index, recipe in enumerate(results, 1):
            print(f"  {index}. {recipe.get('title', '')[:80]}")

        semantic_hits = sum(
            1 for recipe in results if _title_matches_intent(recipe.get("title", ""), query)
        )
        ok = semantic_hits >= min(2, len(results))
        print(f"  Intent matches: {semantic_hits}/{len(results)} -> {'PASS' if ok else 'FAIL'}")
        if ok:
            passed += 1

    print(f"\nPhase A probe: {passed}/{len(PROBE_QUERIES)} queries passed")
    return passed == len(PROBE_QUERIES)


if __name__ == "__main__":
    success = run_probes()
    sys.exit(0 if success else 1)
