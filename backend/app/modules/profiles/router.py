"""Роутер для управления профилями пользователя."""

from fastapi import APIRouter, HTTPException

from app.modules.profiles.repository import (
    create_profile,
    delete_profile,
    get_default_profile,
    get_profile,
    list_profiles,
    update_profile,
)
from app.modules.profiles.schemas import ProfileCreate, ProfileOut, ProfileUpdate

router = APIRouter()


@router.get("/api/profiles", response_model=list[ProfileOut])
async def get_profiles():
    """Возвращает список всех профилей."""
    return await list_profiles()


@router.post("/api/profiles", response_model=ProfileOut, status_code=201)
async def create_new_profile(data: ProfileCreate):
    """Создаёт новый профиль."""
    return await create_profile(
        name=data.name,
        system_prompt=data.system_prompt,
        is_default=data.is_default,
    )


@router.get("/api/profiles/default", response_model=ProfileOut)
async def get_default():
    """Возвращает дефолтный профиль."""
    profile = await get_default_profile()
    if profile is None:
        raise HTTPException(status_code=404, detail="Дефолтный профиль не найден")
    return profile


@router.get("/api/profiles/{profile_id}", response_model=ProfileOut)
async def get_profile_by_id(profile_id: str):
    """Возвращает профиль по ID."""
    profile = await get_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Профиль не найден")
    return profile


@router.put("/api/profiles/{profile_id}", response_model=ProfileOut)
async def update_existing_profile(profile_id: str, data: ProfileUpdate):
    """Обновляет профиль."""
    fields = data.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="Нет полей для обновления")
    profile = await update_profile(profile_id, **fields)
    if profile is None:
        raise HTTPException(status_code=404, detail="Профиль не найден")
    return profile


@router.delete("/api/profiles/{profile_id}", status_code=204)
async def delete_existing_profile(profile_id: str):
    """Удаляет профиль."""
    deleted = await delete_profile(profile_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Профиль не найден")
