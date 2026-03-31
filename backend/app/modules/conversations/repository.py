"""Репозиторий для работы с диалогами и сообщениями.

Все операции с таблицами conversations и messages.
"""

import json
import uuid

from sqlalchemy import select, update

from app.core.database import _now_iso, async_session
from app.models import Conversation, Message


# --- Диалоги ---


async def create_conversation(title: str = "Новый диалог", profile_id: str | None = None) -> dict:
    """Создаёт новый диалог и возвращает его данные."""
    now = _now_iso()
    conv = Conversation(
        id=str(uuid.uuid4()),
        title=title,
        created_at=now,
        updated_at=now,
        profile_id=profile_id,
    )
    async with async_session() as session:
        session.add(conv)
        await session.commit()
    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
    }


async def list_conversations() -> list[dict]:
    """Возвращает список диалогов, отсортированных по дате обновления."""
    async with async_session() as session:
        result = await session.execute(
            select(Conversation).order_by(Conversation.updated_at.desc())
        )
        rows = result.scalars().all()
    return [
        {"id": r.id, "title": r.title, "updated_at": r.updated_at}
        for r in rows
    ]


async def get_conversation(conversation_id: str) -> dict | None:
    """Возвращает диалог по ID или None если не найден."""
    async with async_session() as session:
        conv = await session.get(Conversation, conversation_id)
    if conv is None:
        return None
    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
    }


async def delete_conversation(conversation_id: str) -> bool:
    """Удаляет диалог и все связанные данные (CASCADE). Возвращает True если удалён."""
    async with async_session() as session:
        conv = await session.get(Conversation, conversation_id)
        if conv is None:
            return False
        await session.delete(conv)
        await session.commit()
    return True


async def update_conversation_title(conversation_id: str, title: str) -> None:
    """Обновляет название диалога."""
    async with async_session() as session:
        await session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(title=title, updated_at=_now_iso())
        )
        await session.commit()


# --- Сообщения ---


async def add_message(
    conversation_id: str,
    role: str,
    content: str,
    usage_json: str | None = None,
) -> int:
    """Добавляет сообщение в диалог и обновляет updated_at диалога."""
    now = _now_iso()
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        usage_json=usage_json,
        created_at=now,
    )
    async with async_session() as session:
        session.add(msg)
        # Обновляем время последнего изменения диалога
        await session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=now)
        )
        await session.commit()
    return msg.id


async def get_messages(conversation_id: str) -> list[dict]:
    """Возвращает все сообщения диалога в хронологическом порядке."""
    async with async_session() as session:
        result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.id.asc())
        )
        rows = result.scalars().all()
    messages = []
    for r in rows:
        msg = {
            "id": r.id,
            "role": r.role,
            "content": r.content,
            "created_at": r.created_at,
        }
        if r.usage_json:
            msg["usage"] = json.loads(r.usage_json)
        messages.append(msg)
    return messages


async def get_messages_with_ids(conversation_id: str) -> list[dict]:
    """Возвращает все сообщения диалога с их id (для управления контекстом)."""
    async with async_session() as session:
        result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.id.asc())
        )
        rows = result.scalars().all()
    messages = []
    for r in rows:
        msg = {
            "id": r.id,
            "role": r.role,
            "content": r.content,
            "created_at": r.created_at,
        }
        if r.usage_json:
            msg["usage"] = json.loads(r.usage_json)
        messages.append(msg)
    return messages


async def add_message_to_branch(
    conversation_id: str,
    branch_id: int,
    role: str,
    content: str,
    usage_json: str | None = None,
) -> int:
    """Добавляет сообщение в конкретную ветку."""
    now = _now_iso()
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        usage_json=usage_json,
        created_at=now,
        branch_id=branch_id,
    )
    async with async_session() as session:
        session.add(msg)
        await session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=now)
        )
        await session.commit()
    return msg.id
