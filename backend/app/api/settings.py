from fastapi import APIRouter
from app.models.db_models import Category

router = APIRouter(prefix="/settings", tags=["Settings"])

@router.get("/categories")
def get_categories():
    return [c.value for c in Category]
