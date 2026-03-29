"""Сервис базы данных для хранения истории диалогов.

Использует SQLAlchemy 2.0 async с aiosqlite в качестве драйвера.
Управляет таблицами conversations, messages и summaries.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text as sqlalchemy_text, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.models import Base, Branch, Conversation, ConversationFact, Message, Summary

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
    """Инициализирует БД: создаёт директорию, таблицы и добавляет недостающие колонки."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Миграция: добавляем новые колонки в существующие таблицы (если их нет)
        await _migrate_add_columns(conn)


async def _migrate_add_columns(conn) -> None:
    """Добавляет новые колонки в существующие таблицы (ALTER TABLE IF NOT EXISTS)."""
    migrations = [
        ("conversations", "context_strategy", "TEXT DEFAULT 'summary'"),
        ("conversations", "active_branch_id", "INTEGER"),
        ("messages", "branch_id", "INTEGER"),
    ]
    for table, column, col_type in migrations:
        try:
            await conn.execute(
                sqlalchemy_text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            )
        except Exception:
            # Колонка уже существует — пропускаем
            pass


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


# --- Стратегия контекста ---


async def get_conversation_strategy(conversation_id: str) -> str:
    """Возвращает текущую стратегию контекста для диалога."""
    async with async_session() as session:
        conv = await session.get(Conversation, conversation_id)
    if conv is None:
        return "summary"
    return conv.context_strategy or "summary"


async def set_conversation_strategy(conversation_id: str, strategy: str) -> None:
    """Устанавливает стратегию контекста для диалога."""
    async with async_session() as session:
        await session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(context_strategy=strategy, updated_at=_now_iso())
        )
        await session.commit()


# --- Facts (Sticky Facts) ---


async def get_facts(conversation_id: str) -> list[dict]:
    """Возвращает все факты диалога."""
    async with async_session() as session:
        result = await session.execute(
            select(ConversationFact)
            .where(ConversationFact.conversation_id == conversation_id)
            .order_by(ConversationFact.key.asc())
        )
        rows = result.scalars().all()
    return [
        {"key": r.key, "value": r.value, "updated_at": r.updated_at}
        for r in rows
    ]


async def set_fact(conversation_id: str, key: str, value: str) -> None:
    """Создаёт или обновляет факт (upsert по ключу)."""
    now = _now_iso()
    async with async_session() as session:
        # Ищем существующий факт
        result = await session.execute(
            select(ConversationFact)
            .where(
                ConversationFact.conversation_id == conversation_id,
                ConversationFact.key == key,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.value = value
            existing.updated_at = now
        else:
            fact = ConversationFact(
                conversation_id=conversation_id,
                key=key,
                value=value,
                created_at=now,
                updated_at=now,
            )
            session.add(fact)
        await session.commit()


async def delete_fact(conversation_id: str, key: str) -> bool:
    """Удаляет факт по ключу. Возвращает True если удалён."""
    async with async_session() as session:
        result = await session.execute(
            select(ConversationFact)
            .where(
                ConversationFact.conversation_id == conversation_id,
                ConversationFact.key == key,
            )
        )
        fact = result.scalar_one_or_none()
        if fact is None:
            return False
        await session.delete(fact)
        await session.commit()
    return True


# --- Ветки (Branching) ---


async def create_branch(
    conversation_id: str, name: str, checkpoint_message_id: int
) -> dict:
    """Создаёт новую ветку от указанного сообщения (чекпоинта)."""
    branch = Branch(
        conversation_id=conversation_id,
        name=name,
        checkpoint_message_id=checkpoint_message_id,
        created_at=_now_iso(),
    )
    async with async_session() as session:
        session.add(branch)
        await session.commit()
        # Устанавливаем эту ветку как активную
        await session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(active_branch_id=branch.id, updated_at=_now_iso())
        )
        await session.commit()
    return {
        "id": branch.id,
        "name": branch.name,
        "checkpoint_message_id": branch.checkpoint_message_id,
        "created_at": branch.created_at,
    }


async def get_branches(conversation_id: str) -> list[dict]:
    """Возвращает все ветки диалога."""
    async with async_session() as session:
        result = await session.execute(
            select(Branch)
            .where(Branch.conversation_id == conversation_id)
            .order_by(Branch.created_at.asc())
        )
        rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "checkpoint_message_id": r.checkpoint_message_id,
            "created_at": r.created_at,
        }
        for r in rows
    ]


async def get_active_branch_id(conversation_id: str) -> int | None:
    """Возвращает ID активной ветки (или None если нет)."""
    async with async_session() as session:
        conv = await session.get(Conversation, conversation_id)
    if conv is None:
        return None
    return conv.active_branch_id


async def set_active_branch(conversation_id: str, branch_id: int) -> None:
    """Переключает активную ветку."""
    async with async_session() as session:
        await session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(active_branch_id=branch_id, updated_at=_now_iso())
        )
        await session.commit()


async def get_branch_messages(conversation_id: str, branch_id: int) -> list[dict]:
    """Возвращает сообщения ветки: общие (до чекпоинта) + сообщения ветки."""
    async with async_session() as session:
        # Находим чекпоинт ветки
        branch_result = await session.execute(
            select(Branch).where(Branch.id == branch_id)
        )
        branch = branch_result.scalar_one_or_none()
        if branch is None:
            return []

        checkpoint_id = branch.checkpoint_message_id

        # Общие сообщения (до чекпоинта включительно, без branch_id)
        common_result = await session.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.id <= checkpoint_id,
                Message.branch_id.is_(None),
            )
            .order_by(Message.id.asc())
        )
        common_msgs = common_result.scalars().all()

        # Сообщения в ветке (после чекпоинта, с branch_id)
        branch_result = await session.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.branch_id == branch_id,
            )
            .order_by(Message.id.asc())
        )
        branch_msgs = branch_result.scalars().all()

    all_msgs = list(common_msgs) + list(branch_msgs)
    return [
        {"id": m.id, "role": m.role, "content": m.content}
        for m in all_msgs
    ]


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
