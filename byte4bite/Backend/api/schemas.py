from pydantic import BaseModel
from typing import List, Optional

# This defines what a Recipe looks like for the computer
class RecipeBase(BaseModel):
    title: str
    description: str
    ingredients: List[str]
    instructions: List[str]
    prep_time: str = "20 mins"
    difficulty: str = "Easy"
    dietary_tags: List[str] = []

class RecipeResponse(RecipeBase):
    id: Optional[int] = None

    class Config:
        from_attributes = True