import os
from pathlib import Path

from dotenv import load_dotenv

# Load Backend/.env before any service reads GEMINI_API_KEY
load_dotenv(Path(__file__).resolve().parent / ".env")

AUTO_INGEST_ON_STARTUP = os.getenv("AUTO_INGEST_ON_STARTUP", "true").lower() in {"1", "true", "yes"}
REFRESH_DATASETS_ON_STARTUP = os.getenv("REFRESH_DATASETS_ON_STARTUP", "false").lower() in {"1", "true", "yes"}
EMBED_ON_INGEST = os.getenv("EMBED_ON_INGEST", "true").lower() in {"1", "true", "yes"}

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api import auth, recipes
from services import recipe_service

app = FastAPI(title="Byte4Bite AI")

@app.on_event("startup")
def startup_load_recipes():
    # Verify MySQL connection, auto-sync new datasets, log corpus size
    from database.connection import ping_database
    if ping_database():
        print("DEBUG: MySQL connection OK")
        if AUTO_INGEST_ON_STARTUP:
            try:
                no_embed = not EMBED_ON_INGEST
                if REFRESH_DATASETS_ON_STARTUP:
                    from rag.ingest import refresh_datasets_from_folder
                    stats = refresh_datasets_from_folder(no_embed=no_embed, clear_saved=True)
                else:
                    from rag.ingest import sync_new_datasets
                    stats = sync_new_datasets(no_embed=no_embed)
                if stats.get("inserted", 0) > 0 or stats.get("removed_old_rows", 0) > 0:
                    recipe_service.invalidate_recipe_cache()
            except Exception as exc:
                print(f"DEBUG: Auto dataset sync failed: {exc}")
        try:
            from database.recipe_repository import RecipeRepository
            embed_stats = RecipeRepository.count_embedding_stats()
            print(
                "DEBUG: Embedding health — "
                f"valid={embed_stats['valid_embeddings']}, "
                f"needs_backfill={embed_stats['needs_backfill']}, "
                f"corpus={embed_stats['total_corpus']}"
            )
            if embed_stats["needs_backfill"] > 0:
                print("DEBUG: Run: python -m rag.backfill_embeddings")
        except Exception as exc:
            print(f"DEBUG: Embedding health check failed: {exc}")
    else:
        print("DEBUG: MySQL unavailable — check .env and run database/schema.sql")
    recipe_service.preload_recipes()

# CORS — comma-separated origins in .env (default: local Next.js dev)
_cors_raw = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001",
)
CORS_ORIGINS = [origin.strip() for origin in _cors_raw.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Type"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(recipes.router, prefix="/api/recipes", tags=["Recipes"])

@app.get("/")
def read_root():
    return {"message": "Byte4Bite Backend is Online!"}