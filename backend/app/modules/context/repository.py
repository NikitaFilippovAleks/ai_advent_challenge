"""Репозиторий для работы со стратегиями контекста, фактами, ветками и суммаризациями.

Все операции с таблицами conversation_facts, branches, summaries
и полями context_strategy/active_branch_id в conversations.
"""

from sqlalchemy import select, update

from app.core.database import _now_iso, async_session
from app.models import Branch, Conversation, ConversationFact, Message, Summary


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


# --- Факты (Sticky Facts) ---


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
