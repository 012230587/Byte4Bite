from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api import recipes
from services import recipe_service

app = FastAPI(title="Byte4Bite AI")

@app.on_event("startup")
def startup_load_recipes():
    # Preload and clean datasets using heuristic column mapping
    recipe_service.preload_recipes()

# This is the "Security Pass"
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"], # Allows your frontend to talk to it
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(recipes.router, prefix="/api/recipes", tags=["Recipes"])

@app.get("/")
def read_root():
    return {"message": "Byte4Bite Backend is Online!"}