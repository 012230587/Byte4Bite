from pydantic import BaseModel, Field
from typing import List, Optional

class RecipeBase(BaseModel):
    title: str
    description: str
    ingredients: List[str]
    instructions: List[str]
    prep_time: str = "20 mins"
    difficulty: str = "Easy"
    dietary_tags: List[str] = []
    cuisine: Optional[str] = None
    is_generated: Optional[bool] = None
    similarity_score: Optional[float] = None
    search_mode: Optional[str] = None
    inspired_by: Optional[List[str]] = None
    retrieval_note: Optional[str] = None

class RecipeResponse(RecipeBase):
    id: Optional[int] = None

    class Config:
        from_attributes = True


class GenerateRecipeResponse(BaseModel):
    recipes: List[RecipeResponse]
    is_generated: bool = True
    inspired_by: List[str] = Field(default_factory=list)
    retrieval_note: Optional[str] = None
    bot_message: Optional[str] = None
    rag_sample_count: int = 0
    error: Optional[str] = None