"""Стратегия Sticky Facts — ключевые факты + последние N сообщений.

Факты извлекаются автоматически после каждого ответа LLM.
"""

import json
import logging

from app.core.config import settings
from app.modules.context.repository import get_facts, set_fact
from app.modules.context.strategies.base import BaseContextStrategy
from app.modules.conversations.repository import get_messages_with_ids
from app.shared.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class StickyFactsStrategy(BaseContextStrategy):
    """Ключевые факты + последние N сообщений."""

    def __init__(self, llm: BaseLLMProvider) -> None:
        self._llm = llm

    async def build_context(self, conversation_id: str) -> list[dict]:
        """Формирует системное сообщение с фактами, затем последние N сообщений."""
        all_messages = await get_messages_with_ids(conversation_id)
        facts = await get_facts(conversation_id)
        n = settings.context_recent_count
        recent = all_messages[-n:] if len(all_messages) > n else all_messages

        result = []

        # Системное сообщение с фактами (если есть)
        if facts:
            facts_text = "\n".join(f"- {f['key']}: {f['value']}" for f in facts)
            result.append({
                "role": "system",
                "content": (
                    "Ключевые факты из диалога (используй как контекст):\n\n"
                    f"{facts_text}"
                ),
            })

        # Последние N сообщений
        for m in recent:
            result.append({"role": m["role"], "content": m["content"]})

        return result

    async def extract_and_update_facts(
        self, conversation_id: str, user_text: str, assistant_text: str
    ) -> None:
        """Извлекает факты из последнего обмена и обновляет в БД.

        Вызывается после каждого ответа LLM при стратегии sticky_facts.
        """
        existing_facts = await get_facts(conversation_id)

        # Формируем контекст для извлечения фактов
        facts_context = ""
        if existing_facts:
            facts_context = "Текущие факты:\n" + "\n".join(
                f"- {f['key']}: {f['value']}" for f in existing_facts
            ) + "\n\n"

        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "Ты извлекаешь ключевые факты из диалога. "
                    "Верни JSON-объект с парами ключ-значение. "
                    "Ключи — короткие названия на русском "
                    "(цель, ограничения, предпочтения, решения и т.д.). "
                    "Значения — краткие описания. "
                    "Обнови существующие факты если информация изменилась, "
                    "добавь новые если есть. "
                    "Верни ТОЛЬКО JSON без пояснений.\n\n"
                    f"{facts_context}"
                    "Последний обмен:\n"
                    f"Пользователь: {user_text}\n"
                    f"Ассистент: {assistant_text}"
                ),
            },
            {
                "role": "user",
                "content": "Извлеки ключевые факты из этого обмена в формате JSON.",
            },
        ]

        try:
            result = await self._llm.chat(
                prompt_messages,
                model=settings.context_summary_model,
                temperature=0.1,
            )
            # Парсим JSON из ответа
            content = result["content"].strip()
            # Убираем возможные обёртки ```json ... ```
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            facts_dict = json.loads(content)
            if isinstance(facts_dict, dict):
                for key, value in facts_dict.items():
                    await set_fact(conversation_id, str(key), str(value))
        except Exception as e:
            logger.warning("Ошибка извлечения фактов: %s", e)
