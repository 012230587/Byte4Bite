from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional

from api.deps import get_current_user_id
from database.user_repository import UserRepository
from services.auth_service import (
    create_access_token,
    hash_password,
    verify_password,
)
from services.profile_cache import get_cached_profile, invalidate_profile, set_cached_profile

router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ProfileUpdateRequest(BaseModel):
    dietary_restriction: Optional[str] = None
    allergies: Optional[List[str]] = None
    health_goals: Optional[List[str]] = None


class SaveRecipeRequest(BaseModel):
    recipe: dict
    notes: Optional[str] = ""


def _load_profile(user_id: int) -> dict:
    cached = get_cached_profile(user_id)
    if cached:
        return cached
    profile = UserRepository.get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    set_cached_profile(user_id, profile)
    return profile


@router.post("/register")
async def register(body: RegisterRequest):
    try:
        if UserRepository.email_exists(body.email):
            raise HTTPException(status_code=400, detail="Email already registered")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database error: {exc}") from exc
    user_id = UserRepository.create_user(body.email, hash_password(body.password))
    token = create_access_token(user_id, body.email)
    return {
        "success": True,
        "user_id": user_id,
        "email": body.email,
        "access_token": token,
        "token_type": "bearer",
    }


@router.post("/login")
async def login(body: LoginRequest):
    user = UserRepository.get_user_by_email(body.email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["user_id"], user["email"])
    return {
        "success": True,
        "user_id": user["user_id"],
        "email": user["email"],
        "access_token": token,
        "token_type": "bearer",
    }


@router.get("/me")
async def get_me(user_id: int = Depends(get_current_user_id)):
    profile = _load_profile(user_id)
    return {
        "success": True,
        "user_id": profile["user_id"],
        "email": profile["email"],
        "profile": {
            "dietary_restriction": profile.get("dietary_restriction"),
            "allergies": profile.get("allergies") or [],
            "health_goals": profile.get("health_goals") or [],
        },
    }


@router.get("/profile")
async def get_profile(user_id: int = Depends(get_current_user_id)):
    profile = _load_profile(user_id)
    return {"success": True, "profile": profile}


@router.put("/profile")
async def update_profile(
    body: ProfileUpdateRequest,
    user_id: int = Depends(get_current_user_id),
):
    UserRepository.update_profile(
        user_id,
        dietary_restriction=body.dietary_restriction,
        allergies=body.allergies,
        health_goals=body.health_goals,
    )
    invalidate_profile(user_id)
    profile = UserRepository.get_profile(user_id)
    set_cached_profile(user_id, profile)
    return {"success": True, "profile": profile}


@router.post("/saved-recipes")
async def save_recipe(
    body: SaveRecipeRequest,
    user_id: int = Depends(get_current_user_id),
):
    try:
        saved = UserRepository.save_recipe_for_user(user_id, body.recipe, body.notes or "")
        return {"success": True, "saved_recipe": saved}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/saved-recipes")
async def list_saved_recipes(user_id: int = Depends(get_current_user_id)):
    recipes = UserRepository.list_saved_recipes(user_id)
    return {"success": True, "recipes": recipes, "count": len(recipes)}
