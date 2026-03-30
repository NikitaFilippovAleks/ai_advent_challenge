"""API-эндпоинты для управления стратегиями контекста, фактами и ветками."""

from fastapi import APIRouter, HTTPException

from app.modules.context.repository import (
    create_branch,
    delete_fact,
    get_active_branch_id,
    get_branches,
    get_conversation_strategy,
    get_facts,
    set_active_branch,
    set_conversation_strategy,
    set_fact,
)
from app.modules.context.schemas import (
    BranchRequest,
    FactRequest,
    StrategyRequest,
    VALID_STRATEGIES,
)
from app.modules.conversations.repository import get_messages_with_ids

router = APIRouter()


# --- Стратегия контекста ---


@router.get("/api/conversations/{conversation_id}/strategy")
async def get_strategy(conversation_id: str):
    """Возвращает текущую стратегию контекста для диалога."""
    strategy = await get_conversation_strategy(conversation_id)
    return {"strategy": strategy}


@router.put("/api/conversations/{conversation_id}/strategy")
async def update_strategy(conversation_id: str, request: StrategyRequest):
    """Устанавливает стратегию контекста для диалога."""
    if request.strategy not in VALID_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"Неизвестная стратегия: {request.strategy}. "
                   f"Доступные: {', '.join(VALID_STRATEGIES)}",
        )
    await set_conversation_strategy(conversation_id, request.strategy)
    return {"strategy": request.strategy}


# --- Факты (Sticky Facts) ---


@router.get("/api/conversations/{conversation_id}/facts")
async def list_facts(conversation_id: str):
    """Возвращает все факты диалога."""
    facts = await get_facts(conversation_id)
    return {"facts": facts}


@router.put("/api/conversations/{conversation_id}/facts")
async def upsert_fact(conversation_id: str, request: FactRequest):
    """Создаёт или обновляет факт."""
    await set_fact(conversation_id, request.key, request.value)
    return {"key": request.key, "value": request.value}


@router.delete("/api/conversations/{conversation_id}/facts/{key}")
async def remove_fact(conversation_id: str, key: str):
    """Удаляет факт по ключу."""
    deleted = await delete_fact(conversation_id, key)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Факт '{key}' не найден")
    return {"deleted": key}


# --- Ветки (Branching) ---


@router.get("/api/conversations/{conversation_id}/branches")
async def list_branches(conversation_id: str):
    """Возвращает все ветки диалога + ID активной ветки."""
    branches = await get_branches(conversation_id)
    active_id = await get_active_branch_id(conversation_id)
    return {"branches": branches, "active_branch_id": active_id}


@router.post("/api/conversations/{conversation_id}/branches")
async def create_new_branch(conversation_id: str, request: BranchRequest):
    """Создаёт новую ветку от указанного сообщения (чекпоинта)."""
    # Проверяем, что checkpoint_message_id существует
    messages = await get_messages_with_ids(conversation_id)
    msg_ids = {m["id"] for m in messages}
    if request.checkpoint_message_id not in msg_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Сообщение с ID {request.checkpoint_message_id} не найдено",
        )
    branch = await create_branch(
        conversation_id, request.name, request.checkpoint_message_id
    )
    return branch


@router.put("/api/conversations/{conversation_id}/branches/{branch_id}/activate")
async def activate_branch(conversation_id: str, branch_id: int):
    """Переключает активную ветку."""
    branches = await get_branches(conversation_id)
    branch_ids = {b["id"] for b in branches}
    if branch_id not in branch_ids:
        raise HTTPException(
            status_code=404, detail=f"Ветка с ID {branch_id} не найдена"
        )
    await set_active_branch(conversation_id, branch_id)
    return {"active_branch_id": branch_id}
