"""Стратегия Memory — 3-уровневая память + последние N сообщений.

Формирует контекст от стабильного к эфемерному:
1. Долгосрочная память (кросс-диалоговая)
2. Рабочая память (данные текущей задачи)
3. Краткосрочная память (наблюдения текущего диалога)
4. Последние N сообщений
"""

from app.core.config import settings
from app.modules.context.strategies.base import BaseContextStrategy
from app.modules.conversations.repository import get_messages_with_ids
from app.modules.memory.repository import (
    get_insights,
    get_long_term_memories,
    get_working_memory,
)


class MemoryStrategy(BaseContextStrategy):
    """Трёхуровневая память + последние N сообщений."""

    async def build_context(self, conversation_id: str) -> list[dict]:
        """Формирует контекст из всех 3 уровней памяти и недавних сообщений."""
        all_messages = await get_messages_with_ids(conversation_id)
        long_term = await get_long_term_memories()
        working = await get_working_memory(conversation_id)
        insights = await get_insights(conversation_id)

        n = settings.context_recent_count
        recent = all_messages[-n:] if len(all_messages) > n else all_messages

        result = []

        # 1. Долгосрочная память (самая стабильная — идёт первой)
        if long_term:
            # Группируем по категориям
            by_category: dict[str, list[str]] = {}
            for item in long_term:
                cat = item["category"]
                cat_label = {
                    "preference": "Предпочтения",
                    "knowledge": "Знания",
                    "decision": "Решения",
                }.get(cat, cat)
                by_category.setdefault(cat_label, []).append(
                    f"- {item['key']}: {item['value']}"
                )

            sections = []
            for cat_label, items in by_category.items():
                sections.append(f"{cat_label}:\n" + "\n".join(items))

            result.append({
                "role": "system",
                "content": (
                    "ДОЛГОСРОЧНАЯ ПАМЯТЬ (накопленные знания о пользователе):\n\n"
                    + "\n\n".join(sections)
                ),
            })

        # 2. Рабочая память (данные текущей задачи)
        if working:
            by_category: dict[str, list[str]] = {}
            for item in working:
                cat = item["category"]
                cat_label = {
                    "goal": "Цели",
                    "constraint": "Ограничения",
                    "decision": "Решения",
                    "result": "Результаты",
                    "fact": "Факты",
                }.get(cat, cat)
                by_category.setdefault(cat_label, []).append(
                    f"- {item['key']}: {item['value']}"
                )

            sections = []
            for cat_label, items in by_category.items():
                sections.append(f"{cat_label}:\n" + "\n".join(items))

            result.append({
                "role": "system",
                "content": (
                    "РАБОЧАЯ ПАМЯТЬ (данные текущей задачи):\n\n"
                    + "\n\n".join(sections)
                ),
            })

        # 3. Краткосрочная память (эфемерные наблюдения)
        if insights:
            items_text = "\n".join(f"- {i['content']}" for i in insights[-10:])
            result.append({
                "role": "system",
                "content": (
                    "КРАТКОСРОЧНАЯ ПАМЯТЬ (наблюдения текущего диалога):\n\n"
                    + items_text
                ),
            })

        # 4. Последние N сообщений
        for m in recent:
            result.append({"role": m["role"], "content": m["content"]})

        return result
