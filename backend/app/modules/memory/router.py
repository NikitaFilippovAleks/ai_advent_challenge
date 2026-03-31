"""REST API для управления 3-уровневой памятью ассистента.

Краткосрочная: /api/memory/{id}/short-term
Рабочая: /api/memory/{id}/working
Долгосрочная: /api/memory/long-term

ВАЖНО: статические роуты (/long-term/*) объявлены ПЕРЕД динамическими (/{conversation_id}),
иначе FastAPI интерпретирует "long-term" как conversation_id.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.modules.memory.dependencies import get_memory_service
from app.modules.memory.repository import (
    add_insight,
    clear_insights,
    delete_insight,
    delete_long_term_memory,
    delete_working_memory,
    get_insights,
    get_long_term_memories,
    get_working_memory,
    search_long_term_memories,
    set_long_term_memory,
    set_working_memory,
)
from app.modules.memory.schemas import (
    InsightRequest,
    LongTermMemoryRequest,
    WorkingMemoryRequest,
)
from app.modules.memory.service import MemoryService

router = APIRouter(prefix="/api/memory", tags=["memory"])


# === Долгосрочная память (СТАТИЧЕСКИЕ роуты — объявляем ПЕРВЫМИ) ===


@router.get("/long-term/search")
async def search_long_term(
    q: str = Query(..., description="Поисковый запрос"),
):
    """Ищет в долгосрочной памяти по подстроке."""
    results = await search_long_term_memories(q)
    return {"results": results}


@router.get("/long-term")
async def list_long_term(
    category: str | None = Query(None, description="Фильтр по категории"),
):
    """Возвращает все записи долгосрочной памяти."""
    items = await get_long_term_memories(category)
    return {"long_term": items}


@router.put("/long-term")
async def upsert_long_term(body: LongTermMemoryRequest):
    """Создаёт или обновляет запись долгосрочной памяти."""
    await set_long_term_memory(body.key, body.value, body.category)
    return {"ok": True}


@router.delete("/long-term/{memory_id}")
async def remove_long_term(memory_id: int):
    """Удаляет запись долгосрочной памяти по ID."""
    deleted = await delete_long_term_memory(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return {"ok": True}


# === Объединённый эндпоинт (динамический — ПОСЛЕ статических) ===


@router.get("/{conversation_id}")
async def get_all_memory(
    conversation_id: str,
    service: MemoryService = Depends(get_memory_service),
):
    """Возвращает все 3 уровня памяти для диалога."""
    return await service.get_all_memory(conversation_id)


# === Краткосрочная память ===


@router.get("/{conversation_id}/short-term")
async def list_insights(conversation_id: str):
    """Возвращает все краткосрочные наблюдения диалога."""
    insights = await get_insights(conversation_id)
    return {"insights": insights}


@router.post("/{conversation_id}/short-term")
async def create_insight(conversation_id: str, body: InsightRequest):
    """Добавляет краткосрочное наблюдение вручную."""
    insight_id = await add_insight(conversation_id, body.content)
    return {"id": insight_id}


@router.delete("/{conversation_id}/short-term/{insight_id}")
async def remove_insight(conversation_id: str, insight_id: int):
    """Удаляет краткосрочное наблюдение."""
    deleted = await delete_insight(insight_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Наблюдение не найдено")
    return {"ok": True}


@router.delete("/{conversation_id}/short-term")
async def clear_all_insights(conversation_id: str):
    """Очищает все краткосрочные наблюдения диалога."""
    count = await clear_insights(conversation_id)
    return {"deleted": count}


# === Рабочая память ===


@router.get("/{conversation_id}/working")
async def list_working_memory(
    conversation_id: str,
    category: str | None = Query(None, description="Фильтр по категории"),
):
    """Возвращает записи рабочей памяти диалога."""
    items = await get_working_memory(conversation_id, category)
    return {"working": items}


@router.put("/{conversation_id}/working")
async def upsert_working_memory(conversation_id: str, body: WorkingMemoryRequest):
    """Создаёт или обновляет запись рабочей памяти."""
    await set_working_memory(conversation_id, body.key, body.value, body.category)
    return {"ok": True}


@router.delete("/{conversation_id}/working/{key}")
async def remove_working_memory(conversation_id: str, key: str):
    """Удаляет запись рабочей памяти по ключу."""
    deleted = await delete_working_memory(conversation_id, key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return {"ok": True}
