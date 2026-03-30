"""Стратегия Sliding Window — только последние N сообщений."""

from app.core.config import settings
from app.modules.context.strategies.base import BaseContextStrategy
from app.modules.conversations.repository import get_messages_with_ids


class SlidingWindowStrategy(BaseContextStrategy):
    """Скользящее окно: только последние N сообщений, остальное отбрасывается."""

    async def build_context(self, conversation_id: str) -> list[dict]:
        all_messages = await get_messages_with_ids(conversation_id)
        n = settings.context_recent_count
        recent = all_messages[-n:] if len(all_messages) > n else all_messages
        return [{"role": m["role"], "content": m["content"]} for m in recent]
