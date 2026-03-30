"""Роутер для управления диалогами (CRUD)."""

from fastapi import APIRouter, HTTPException

from app.modules.conversations.repository import (
    create_conversation,
    delete_conversation,
    get_conversation,
    get_messages,
    list_conversations,
)
from app.modules.conversations.schemas import ConversationOut, MessageOut

router = APIRouter()


@router.get("/api/conversations", response_model=list[ConversationOut])
async def get_conversations():
    """Возвращает список всех диалогов."""
    return await list_conversations()


@router.post("/api/conversations", response_model=ConversationOut)
async def create_new_conversation():
    """Создаёт новый диалог."""
    conv = await create_conversation()
    return conv


@router.get(
    "/api/conversations/{conversation_id}/messages",
    response_model=list[MessageOut],
)
async def get_conversation_messages(conversation_id: str):
    """Возвращает все сообщения диалога."""
    conv = await get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Диалог не найден")
    return await get_messages(conversation_id)


@router.delete("/api/conversations/{conversation_id}")
async def delete_existing_conversation(conversation_id: str):
    """Удаляет диалог и все его сообщения."""
    deleted = await delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Диалог не найден")
    return {"ok": True}
