"""Стратегия Summary — суммаризация старых сообщений через LLM."""

import logging

from app.core.config import settings
from app.modules.context.repository import add_summary, get_summaries
from app.modules.context.strategies.base import BaseContextStrategy
from app.modules.conversations.repository import get_messages_with_ids
from app.shared.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

# Маппинг ролей для читаемого форматирования
_ROLE_NAMES = {
    "user": "Пользователь",
    "assistant": "Ассистент",
    "system": "Система",
}


class SummaryStrategy(BaseContextStrategy):
    """Суммаризация старых сообщений (по умолчанию).

    Если сообщений мало — возвращает все как есть.
    Иначе: [системное сообщение с суммаризациями] + [последние N сообщений].
    """

    def __init__(self, llm: BaseLLMProvider) -> None:
        self._llm = llm

    async def build_context(self, conversation_id: str) -> list[dict]:
        all_messages = await get_messages_with_ids(conversation_id)

        recent_count = settings.context_recent_count

        # Если сообщений мало — суммаризация не нужна
        if len(all_messages) <= recent_count:
            return [{"role": m["role"], "content": m["content"]} for m in all_messages]

        # Разделяем на старые и последние
        old_messages = all_messages[:-recent_count]
        recent_messages = all_messages[-recent_count:]

        # Получаем уже существующие суммаризации
        existing_summaries = await get_summaries(conversation_id)

        # Определяем, какие старые сообщения ещё не суммаризированы
        last_summarized_id = 0
        if existing_summaries:
            last_summarized_id = max(s["end_message_id"] for s in existing_summaries)

        unsummarized = [m for m in old_messages if m["id"] > last_summarized_id]

        # Суммаризируем блоками, если накопилось достаточно
        block_size = settings.context_summary_block_size
        while len(unsummarized) >= block_size:
            block = unsummarized[:block_size]
            unsummarized = unsummarized[block_size:]

            summary_text = await self._summarize_block(block)
            await add_summary(
                conversation_id,
                summary_text,
                start_message_id=block[0]["id"],
                end_message_id=block[-1]["id"],
            )
            existing_summaries.append({
                "summary": summary_text,
                "start_message_id": block[0]["id"],
                "end_message_id": block[-1]["id"],
            })

        # Собираем финальный контекст
        result = []

        # Системное сообщение с суммаризациями (если есть)
        if existing_summaries:
            summaries_text = "\n\n".join(s["summary"] for s in existing_summaries)
            result.append({
                "role": "system",
                "content": (
                    "Краткое содержание предыдущего разговора:\n\n"
                    f"{summaries_text}"
                ),
            })

        # Несуммаризированные старые сообщения (неполный блок) — добавляем как есть
        for m in unsummarized:
            result.append({"role": m["role"], "content": m["content"]})

        # Последние N сообщений — как есть
        for m in recent_messages:
            result.append({"role": m["role"], "content": m["content"]})

        return result

    async def _summarize_block(self, messages: list[dict]) -> str:
        """Суммаризирует блок сообщений через LLM."""
        formatted = self._format_messages_for_summary(messages)

        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "Кратко перескажи следующий фрагмент диалога между "
                    "пользователем и ассистентом. "
                    "Сохрани ключевые факты, решения и контекст. "
                    "Ответь 2-4 предложениями."
                ),
            },
            {
                "role": "user",
                "content": formatted,
            },
        ]

        try:
            result = await self._llm.chat(
                prompt_messages,
                model=settings.context_summary_model,
                temperature=0.3,
            )
            return result["content"]
        except Exception as e:
            logger.warning(
                "Ошибка суммаризации, используем простое сокращение: %s", e
            )
            # Запасной вариант: просто берём первые слова каждого сообщения
            return self._fallback_summary(messages)

    @staticmethod
    def _format_messages_for_summary(messages: list[dict]) -> str:
        """Форматирует блок сообщений в читаемый текст для суммаризации."""
        lines = []
        for m in messages:
            role_name = _ROLE_NAMES.get(m["role"], m["role"])
            lines.append(f"{role_name}: {m['content']}")
        return "\n".join(lines)

    @staticmethod
    def _fallback_summary(messages: list[dict]) -> str:
        """Запасная суммаризация если LLM недоступен — обрезка до первых 50 символов."""
        lines = []
        for m in messages:
            role_name = _ROLE_NAMES.get(m["role"], m["role"])
            content = m["content"][:50]
            if len(m["content"]) > 50:
                content += "..."
            lines.append(f"{role_name}: {content}")
        return "Фрагмент диалога: " + "; ".join(lines)
