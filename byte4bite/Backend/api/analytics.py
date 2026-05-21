from fastapi import APIRouter

router = APIRouter()

@router.get("/summary")
async def get_analytics_summary():
    return {"message": "Analytics data will appear here soon!"}