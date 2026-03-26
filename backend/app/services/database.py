"""Сервис базы данных для хранения истории диалогов.

Использует SQLAlchemy 2.0 async с aiosqlite в качестве драйвера.
Управляет таблицами conversations, messages и summaries.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.models import Base, Conversation, Message, Summary

# Путь к файлу БД: backend/data/chat.db
DB_PATH = Path(__file__).parent.parent.parent / "data" / "chat.db"

# Async-движок и фабрика сессий
engine = create_async_engine(
    f"sqlite+aiosqlite:///{DB_PATH}",
    echo=False,
)
async_session = async_sessionmaker(engine, expire_on_commit=False)


def _now_iso() -> str:
    """Возвращает текущее время в формате ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    """Инициализирует БД: создаёт директорию и таблицы через SQLAlchemy."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# --- Диалоги ---


async def create_conversation(title: str = "Новый диалог") -> dict:
    """Создаёт новый диалог и возвращает его данные."""
    now = _now_iso()
    conv = Conversation(
        id=str(uuid.uuid4()),
        title=title,
        created_at=now,
        updated_at=now,
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


# --- Суммаризации ---


async def get_summaries(conversation_id: str) -> list[dict]:
    """Возвращает все суммаризации диалога в хронологическом порядке."""
    async with async_session() as session:
        result = await session.execute(
            select(Summary)
            .where(Summary.conversation_id == conversation_id)
            .order_by(Summary.start_message_id.asc())
        )
        rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "summary": r.summary,
            "start_message_id": r.start_message_id,
            "end_message_id": r.end_message_id,
        }
        for r in rows
    ]


async def add_summary(
    conversation_id: str,
    summary: str,
    start_message_id: int,
    end_message_id: int,
) -> int:
    """Сохраняет суммаризацию блока сообщений."""
    s = Summary(
        conversation_id=conversation_id,
        summary=summary,
        start_message_id=start_message_id,
        end_message_id=end_message_id,
        created_at=_now_iso(),
    )
    async with async_session() as session:
        session.add(s)
        await session.commit()
    return s.id
