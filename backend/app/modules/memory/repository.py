"""Репозиторий для 3 уровней памяти ассистента.

Краткосрочная — short_term_insights (привязана к диалогу, каскадное удаление).
Рабочая — conversation_facts с фильтрацией по category.
Долгосрочная — long_term_memories (кросс-диалоговая, живёт вечно).
"""

from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import _now_iso, async_session
from app.models import ConversationFact, LongTermMemory, ShortTermInsight


# --- Краткосрочная память (Tier 1) ---


async def get_insights(conversation_id: str) -> list[dict]:
    """Возвращает все краткосрочные наблюдения диалога."""
    async with async_session() as session:
        result = await session.execute(
            select(ShortTermInsight)
            .where(ShortTermInsight.conversation_id == conversation_id)
            .order_by(ShortTermInsight.created_at.asc())
        )
        rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "content": r.content,
            "source_message_id": r.source_message_id,
            "created_at": r.created_at,
        }
        for r in rows
    ]


async def add_insight(
    conversation_id: str, content: str, source_message_id: int | None = None
) -> int:
    """Добавляет краткосрочное наблюдение. Возвращает ID."""
    insight = ShortTermInsight(
        conversation_id=conversation_id,
        content=content,
        source_message_id=source_message_id,
        created_at=_now_iso(),
    )
    async with async_session() as session:
        session.add(insight)
        await session.commit()
    return insight.id


async def delete_insight(insight_id: int) -> bool:
    """Удаляет краткосрочное наблюдение по ID."""
    async with async_session() as session:
        obj = await session.get(ShortTermInsight, insight_id)
        if obj is None:
            return False
        await session.delete(obj)
        await session.commit()
    return True


async def clear_insights(conversation_id: str) -> int:
    """Удаляет все краткосрочные наблюдения диалога. Возвращает количество удалённых."""
    async with async_session() as session:
        result = await session.execute(
            delete(ShortTermInsight)
            .where(ShortTermInsight.conversation_id == conversation_id)
        )
        await session.commit()
    return result.rowcount


async def trim_insights(conversation_id: str) -> None:
    """Обрезает краткосрочные наблюдения до memory_short_term_max (удаляет самые старые)."""
    max_count = settings.memory_short_term_max
    async with async_session() as session:
        result = await session.execute(
            select(ShortTermInsight)
            .where(ShortTermInsight.conversation_id == conversation_id)
            .order_by(ShortTermInsight.created_at.asc())
        )
        rows = result.scalars().all()
        if len(rows) > max_count:
            # Удаляем самые старые
            to_delete = rows[: len(rows) - max_count]
            for row in to_delete:
                await session.delete(row)
            await session.commit()


# --- Рабочая память (Tier 2) — использует conversation_facts ---


async def get_working_memory(
    conversation_id: str, category: str | None = None
) -> list[dict]:
    """Возвращает записи рабочей памяти диалога, опционально фильтруя по категории."""
    async with async_session() as session:
        query = select(ConversationFact).where(
            ConversationFact.conversation_id == conversation_id
        )
        if category:
            query = query.where(ConversationFact.category == category)
        query = query.order_by(ConversationFact.key.asc())
        result = await session.execute(query)
        rows = result.scalars().all()
    return [
        {
            "key": r.key,
            "value": r.value,
            "category": r.category if r.category else "fact",
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


async def set_working_memory(
    conversation_id: str, key: str, value: str, category: str = "fact"
) -> None:
    """Создаёт или обновляет запись рабочей памяти (upsert по ключу)."""
    now = _now_iso()
    async with async_session() as session:
        result = await session.execute(
            select(ConversationFact).where(
                ConversationFact.conversation_id == conversation_id,
                ConversationFact.key == key,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.value = value
            existing.category = category
            existing.updated_at = now
        else:
            fact = ConversationFact(
                conversation_id=conversation_id,
                key=key,
                value=value,
                category=category,
                created_at=now,
                updated_at=now,
            )
            session.add(fact)
        await session.commit()


async def delete_working_memory(conversation_id: str, key: str) -> bool:
    """Удаляет запись рабочей памяти по ключу."""
    async with async_session() as session:
        result = await session.execute(
            select(ConversationFact).where(
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


# --- Долгосрочная память (Tier 3) ---


async def get_long_term_memories(category: str | None = None) -> list[dict]:
    """Возвращает все записи долгосрочной памяти, опционально фильтруя по категории."""
    async with async_session() as session:
        query = select(LongTermMemory).order_by(LongTermMemory.key.asc())
        if category:
            query = query.where(LongTermMemory.category == category)
        result = await session.execute(query)
        rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "category": r.category,
            "key": r.key,
            "value": r.value,
            "source_conversation_id": r.source_conversation_id,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


async def set_long_term_memory(
    key: str,
    value: str,
    category: str,
    source_conversation_id: str | None = None,
) -> None:
    """Создаёт или обновляет запись долгосрочной памяти (upsert по ключу)."""
    now = _now_iso()
    async with async_session() as session:
        result = await session.execute(
            select(LongTermMemory).where(LongTermMemory.key == key)
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.value = value
            existing.category = category
            existing.updated_at = now
        else:
            memory = LongTermMemory(
                key=key,
                value=value,
                category=category,
                source_conversation_id=source_conversation_id,
                created_at=now,
                updated_at=now,
            )
            session.add(memory)
        await session.commit()


async def delete_long_term_memory(memory_id: int) -> bool:
    """Удаляет запись долгосрочной памяти по ID."""
    async with async_session() as session:
        obj = await session.get(LongTermMemory, memory_id)
        if obj is None:
            return False
        await session.delete(obj)
        await session.commit()
    return True


async def search_long_term_memories(query: str) -> list[dict]:
    """Ищет в долгосрочной памяти по подстроке в ключе или значении."""
    pattern = f"%{query}%"
    async with async_session() as session:
        result = await session.execute(
            select(LongTermMemory)
            .where(
                LongTermMemory.key.ilike(pattern)
                | LongTermMemory.value.ilike(pattern)
            )
            .order_by(LongTermMemory.key.asc())
        )
        rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "category": r.category,
            "key": r.key,
            "value": r.value,
            "source_conversation_id": r.source_conversation_id,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]
