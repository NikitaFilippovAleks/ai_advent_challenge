"""Репозиторий для CRUD-операций с инвариантами."""

import uuid

from sqlalchemy import select

from app.core.database import _now_iso, async_session
from app.models import Invariant


async def create_invariant(
    name: str,
    description: str,
    category: str = "business",
    is_active: bool = True,
    priority: int = 0,
) -> dict:
    """Создаёт инвариант."""
    now = _now_iso()
    inv = Invariant(
        id=str(uuid.uuid4()),
        name=name,
        description=description,
        category=category,
        is_active=is_active,
        priority=priority,
        created_at=now,
        updated_at=now,
    )
    async with async_session() as session:
        session.add(inv)
        await session.commit()
    return _invariant_to_dict(inv)


async def list_invariants() -> list[dict]:
    """Возвращает все инварианты, отсортированные по приоритету (убывание) и имени."""
    async with async_session() as session:
        result = await session.execute(
            select(Invariant).order_by(Invariant.priority.desc(), Invariant.name)
        )
        rows = result.scalars().all()
    return [_invariant_to_dict(r) for r in rows]


async def get_invariant(invariant_id: str) -> dict | None:
    """Возвращает инвариант по ID или None."""
    async with async_session() as session:
        inv = await session.get(Invariant, invariant_id)
    if inv is None:
        return None
    return _invariant_to_dict(inv)


async def update_invariant(invariant_id: str, **fields) -> dict | None:
    """Обновляет поля инварианта."""
    async with async_session() as session:
        inv = await session.get(Invariant, invariant_id)
        if inv is None:
            return None
        for key, value in fields.items():
            if value is not None:
                setattr(inv, key, value)
        inv.updated_at = _now_iso()
        await session.commit()
    return _invariant_to_dict(inv)


async def delete_invariant(invariant_id: str) -> bool:
    """Удаляет инвариант. Возвращает True если удалён."""
    async with async_session() as session:
        inv = await session.get(Invariant, invariant_id)
        if inv is None:
            return False
        await session.delete(inv)
        await session.commit()
    return True


async def toggle_invariant(invariant_id: str) -> dict | None:
    """Переключает is_active (вкл/выкл)."""
    async with async_session() as session:
        inv = await session.get(Invariant, invariant_id)
        if inv is None:
            return None
        inv.is_active = not inv.is_active
        inv.updated_at = _now_iso()
        await session.commit()
    return _invariant_to_dict(inv)


async def get_active_invariants() -> list[dict]:
    """Возвращает только активные инварианты (для инъекции в LLM)."""
    async with async_session() as session:
        result = await session.execute(
            select(Invariant)
            .where(Invariant.is_active == True)
            .order_by(Invariant.priority.desc(), Invariant.name)
        )
        rows = result.scalars().all()
    return [_invariant_to_dict(r) for r in rows]


def _invariant_to_dict(inv: Invariant) -> dict:
    """Конвертирует ORM-объект в словарь."""
    return {
        "id": inv.id,
        "name": inv.name,
        "description": inv.description,
        "category": inv.category,
        "is_active": bool(inv.is_active),
        "priority": inv.priority,
        "created_at": inv.created_at,
        "updated_at": inv.updated_at,
    }
