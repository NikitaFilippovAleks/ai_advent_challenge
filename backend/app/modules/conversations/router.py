"""Роутер для управления диалогами (CRUD)."""

from fastapi import APIRouter, HTTPException

from app.core.database import _now_iso, async_session
from app.models import Conversation
from app.modules.conversations.dependencies import resolve_conversation_profile
from app.modules.conversations.repository import (
    create_conversation,
    delete_conversation,
    get_conversation,
    get_messages,
    list_conversations,
)
from app.modules.conversations.schemas import ConversationOut, MessageOut
from app.modules.profiles.schemas import ConversationProfileOut, SetConversationProfile
from sqlalchemy import update as sql_update

router = APIRouter()


@router.get("/api/conversations", response_model=list[ConversationOut])
async def get_conversations():
    """Возвращает список всех диалогов."""
    return await list_conversations()


@router.post("/api/conversations", response_model=ConversationOut)
async def create_new_conversation():
    """Создаёт новый диалог с дефолтным профилем (если есть)."""
    from app.modules.conversations.dependencies import resolve_conversation_profile
    profile_data = await resolve_conversation_profile(None)
    profile_id = profile_data["profile"]["id"] if profile_data["profile"] else None
    conv = await create_conversation(profile_id=profile_id)
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


@router.get("/api/conversations/{conversation_id}/profile", response_model=ConversationProfileOut)
async def get_conversation_profile(conversation_id: str):
    """Возвращает профиль диалога с указанием источника."""
    async with async_session() as session:
        conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Диалог не найден")
    return await resolve_conversation_profile(conversation.profile_id)


@router.put("/api/conversations/{conversation_id}/profile")
async def set_conversation_profile(conversation_id: str, data: SetConversationProfile):
    """Привязывает профиль к диалогу (или сбрасывает при profile_id=null)."""
    conv = await get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Диалог не найден")

    if data.profile_id:
        profile_data = await resolve_conversation_profile(data.profile_id)
        if profile_data["profile"] is None or profile_data["source"] != "explicit":
            raise HTTPException(status_code=404, detail="Профиль не найден")

    async with async_session() as session:
        await session.execute(
            sql_update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(profile_id=data.profile_id, updated_at=_now_iso())
        )
        await session.commit()
    return {"ok": True}
