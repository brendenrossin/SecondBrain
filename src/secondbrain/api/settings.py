"""Settings API endpoints for user-configurable categories."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from secondbrain.api.dependencies import get_data_path
from secondbrain.settings import load_settings, save_settings

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class CategoryItem(BaseModel):
    name: str
    sub_projects: dict[str, str]


class CategoriesUpdate(BaseModel):
    categories: list[CategoryItem]


@router.get("/categories")
async def get_categories() -> list[dict[str, Any]]:
    """Return the current categories list from settings."""
    data_path = get_data_path()
    settings = load_settings(data_path)
    categories: list[dict[str, Any]] = settings.get("categories", [])
    return categories


@router.put("/categories")
async def update_categories(body: CategoriesUpdate) -> list[dict[str, Any]]:
    """Replace the full categories list."""
    for cat in body.categories:
        if not cat.name.strip():
            raise HTTPException(status_code=422, detail="Category name must be non-empty")

    data_path = get_data_path()
    settings = load_settings(data_path)
    updated: list[dict[str, Any]] = [c.model_dump() for c in body.categories]
    settings["categories"] = updated
    save_settings(data_path, settings)
    return updated
