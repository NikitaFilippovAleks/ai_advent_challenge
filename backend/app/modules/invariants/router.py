"""Роутер для управления инвариантами."""

from fastapi import APIRouter, HTTPException

from app.modules.invariants.repository import (
    create_invariant,
    delete_invariant,
    get_invariant,
    list_invariants,
    toggle_invariant,
    update_invariant,
)
from app.modules.invariants.schemas import InvariantCreate, InvariantOut, InvariantUpdate

router = APIRouter()


@router.get("/api/invariants", response_model=list[InvariantOut])
async def get_invariants():
    """Возвращает список всех инвариантов."""
    return await list_invariants()


@router.post("/api/invariants", response_model=InvariantOut, status_code=201)
async def create_new_invariant(data: InvariantCreate):
    """Создаёт новый инвариант."""
    return await create_invariant(
        name=data.name,
        description=data.description,
        category=data.category,
        is_active=data.is_active,
        priority=data.priority,
    )


@router.get("/api/invariants/{invariant_id}", response_model=InvariantOut)
async def get_invariant_by_id(invariant_id: str):
    """Возвращает инвариант по ID."""
    inv = await get_invariant(invariant_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Инвариант не найден")
    return inv


@router.put("/api/invariants/{invariant_id}", response_model=InvariantOut)
async def update_existing_invariant(invariant_id: str, data: InvariantUpdate):
    """Обновляет инвариант."""
    fields = data.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="Нет полей для обновления")
    inv = await update_invariant(invariant_id, **fields)
    if inv is None:
        raise HTTPException(status_code=404, detail="Инвариант не найден")
    return inv


@router.delete("/api/invariants/{invariant_id}", status_code=204)
async def delete_existing_invariant(invariant_id: str):
    """Удаляет инвариант."""
    deleted = await delete_invariant(invariant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Инвариант не найден")


@router.patch("/api/invariants/{invariant_id}/toggle", response_model=InvariantOut)
async def toggle_invariant_active(invariant_id: str):
    """Переключает активность инварианта (вкл/выкл)."""
    inv = await toggle_invariant(invariant_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Инвариант не найден")
    return inv
