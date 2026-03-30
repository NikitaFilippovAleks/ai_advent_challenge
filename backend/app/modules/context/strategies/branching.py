"""Стратегия Branching — ветки диалога с чекпоинтами."""

from app.modules.context.repository import get_active_branch_id, get_branch_messages
from app.modules.context.strategies.base import BaseContextStrategy
from app.modules.conversations.repository import get_messages_with_ids


class BranchingStrategy(BaseContextStrategy):
    """Ветки диалога: берёт сообщения из активной ветки."""

    async def build_context(self, conversation_id: str) -> list[dict]:
        """Если активной ветки нет — возвращает все сообщения основной линии."""
        branch_id = await get_active_branch_id(conversation_id)

        if branch_id is None:
            # Нет активной ветки — возвращаем все сообщения основной линии
            all_messages = await get_messages_with_ids(conversation_id)
            return [{"role": m["role"], "content": m["content"]} for m in all_messages]

        # Берём сообщения ветки (общие до чекпоинта + ветка)
        messages = await get_branch_messages(conversation_id, branch_id)
        return [{"role": m["role"], "content": m["content"]} for m in messages]
