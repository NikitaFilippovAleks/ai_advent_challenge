"""Сервис памяти ассистента.

Оркестрирует 3 уровня памяти и авто-извлечение через LLM.
Один вызов LLM определяет, что сохранить в каждый уровень.
"""

import json
import logging
import re

from app.core.config import settings
from app.modules.memory.repository import (
    add_insight,
    get_insights,
    get_long_term_memories,
    get_working_memory,
    set_long_term_memory,
    set_working_memory,
    trim_insights,
)
from app.shared.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

# Категории рабочей памяти
WORKING_CATEGORIES = {"goal", "constraint", "decision", "result", "fact"}
# Категории долгосрочной памяти
LONG_TERM_CATEGORIES = {"preference", "knowledge", "decision"}


class MemoryService:
    """Сервис управления трёхуровневой памятью ассистента."""

    def __init__(self, llm: BaseLLMProvider) -> None:
        self._llm = llm

    async def get_all_memory(self, conversation_id: str) -> dict:
        """Возвращает все 3 уровня памяти для диалога."""
        short_term = await get_insights(conversation_id)
        working = await get_working_memory(conversation_id)
        long_term = await get_long_term_memories()
        return {
            "short_term": short_term,
            "working": working,
            "long_term": long_term,
        }

    async def extract_memories(
        self, conversation_id: str, user_text: str, assistant_text: str
    ) -> dict:
        """Извлекает информацию из последнего обмена и распределяет по 3 уровням.

        Один вызов LLM анализирует обмен сообщениями и решает,
        что сохранить в каждый уровень памяти.
        """
        logger.info("=== Начало извлечения памяти для диалога %s ===", conversation_id)

        # Загружаем текущее состояние всех уровней
        try:
            existing_insights = await get_insights(conversation_id)
            existing_working = await get_working_memory(conversation_id)
            existing_long_term = await get_long_term_memories()
            logger.info(
                "Текущее состояние памяти: insights=%d, working=%d, long_term=%d",
                len(existing_insights), len(existing_working), len(existing_long_term),
            )
        except Exception as e:
            logger.error("Ошибка загрузки существующей памяти: %s", e, exc_info=True)
            return {}

        # Формируем контекст существующей памяти
        memory_context = self._build_memory_context(
            existing_insights, existing_working, existing_long_term
        )

        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "Ты система управления памятью ассистента. "
                    "Проанализируй последний обмен сообщениями и определи, "
                    "что нужно запомнить на каждом из 3 уровней.\n\n"
                    "УРОВНИ ПАМЯТИ:\n"
                    "1. short_term — краткосрочные наблюдения о ходе текущего разговора "
                    "(темы, настроение, контекст диалога). Список строк.\n"
                    "2. working — данные текущей задачи: цели, ограничения, решения, "
                    "промежуточные результаты. Объект {ключ: значение}. "
                    f"Допустимые категории ключей: {', '.join(sorted(WORKING_CATEGORIES))}.\n"
                    "3. long_term — стабильные знания о пользователе: предпочтения, "
                    "накопленные знания, важные решения. Объект {ключ: значение}. "
                    "Сохраняй ТОЛЬКО действительно стабильную информацию.\n\n"
                    "ПРАВИЛА:\n"
                    "- Не дублируй уже существующую информацию.\n"
                    "- Обновляй существующие записи если информация изменилась.\n"
                    "- Если нечего добавить на какой-то уровень — оставь пустым.\n"
                    "- Ключи — короткие названия на русском.\n"
                    "- Верни ТОЛЬКО валидный JSON без пояснений.\n\n"
                    f"{memory_context}"
                    "Последний обмен:\n"
                    f"Пользователь: {user_text}\n"
                    f"Ассистент: {assistant_text}"
                ),
            },
            {
                "role": "user",
                "content": (
                    "Верни ТОЛЬКО JSON (без markdown, без пояснений):\n"
                    '{"short_term": ["наблюдение"], "working": {"ключ": "значение"}, '
                    '"long_term": {"ключ": "значение"}}'
                ),
            },
        ]

        try:
            logger.info("Вызываем LLM для извлечения памяти...")
            result = await self._llm.chat(
                prompt_messages,
                model=settings.context_summary_model,
                temperature=0.1,
            )
            raw_content = result["content"].strip()
            logger.info("Ответ LLM (первые 500 символов): %s", raw_content[:500])

            # Извлекаем JSON из ответа (может быть обёрнут в markdown)
            content = self._extract_json(raw_content)
            logger.info("Очищенный JSON: %s", content[:500])

            extracted = json.loads(content)
            if not isinstance(extracted, dict):
                logger.warning("LLM вернул не объект: %s", type(extracted))
                return {}

            logger.info("Парсинг JSON успешен: %s", list(extracted.keys()))

            # Сохраняем краткосрочные наблюдения
            short_term = extracted.get("short_term", [])
            if isinstance(short_term, list):
                saved_count = 0
                for item in short_term:
                    if isinstance(item, str) and item.strip():
                        await add_insight(conversation_id, item.strip())
                        saved_count += 1
                if saved_count > 0:
                    await trim_insights(conversation_id)
                    logger.info("Сохранено %d краткосрочных наблюдений", saved_count)

            # Сохраняем рабочую память
            working = extracted.get("working", {})
            if isinstance(working, dict):
                for key, value in working.items():
                    # Значение может быть не строкой — приводим к строке
                    str_key = str(key).strip()
                    str_value = str(value).strip()
                    if str_key and str_value:
                        category = self._detect_working_category(str_key)
                        await set_working_memory(
                            conversation_id, str_key, str_value, category
                        )
                        logger.info("Рабочая память: [%s] %s = %s", category, str_key, str_value)

            # Сохраняем долгосрочную память
            long_term = extracted.get("long_term", {})
            if isinstance(long_term, dict):
                for key, value in long_term.items():
                    str_key = str(key).strip()
                    str_value = str(value).strip()
                    if str_key and str_value:
                        category = self._detect_long_term_category(str_key)
                        await set_long_term_memory(
                            str_key, str_value, category, conversation_id
                        )
                        logger.info("Долгосрочная память: [%s] %s = %s", category, str_key, str_value)

            logger.info("=== Извлечение памяти завершено успешно ===")
            return extracted

        except json.JSONDecodeError as e:
            logger.error(
                "Ошибка парсинга JSON от LLM: %s\nСодержимое: %s",
                e, raw_content[:1000],  # noqa: F821
            )
            return {}
        except Exception as e:
            logger.error("Ошибка извлечения памяти: %s", e, exc_info=True)
            return {}

    def _extract_json(self, text: str) -> str:
        """Извлекает JSON из текста, убирая markdown-обёртки и лишний текст."""
        # Убираем обёртки ```json ... ```
        if "```" in text:
            # Ищем содержимое между ``` и ```
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
            if match:
                return match.group(1).strip()

        # Ищем JSON-объект в тексте (первый { ... })
        brace_start = text.find("{")
        if brace_start != -1:
            # Находим соответствующую закрывающую скобку
            depth = 0
            for i in range(brace_start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        return text[brace_start:i + 1]

        return text.strip()

    def _build_memory_context(
        self,
        insights: list[dict],
        working: list[dict],
        long_term: list[dict],
    ) -> str:
        """Формирует текстовое описание текущей памяти для промпта."""
        parts = []

        if insights:
            items = "\n".join(f"  - {i['content']}" for i in insights[-10:])
            parts.append(f"Текущая краткосрочная память:\n{items}\n")

        if working:
            items = "\n".join(
                f"  - [{w['category']}] {w['key']}: {w['value']}" for w in working
            )
            parts.append(f"Текущая рабочая память:\n{items}\n")

        if long_term:
            items = "\n".join(
                f"  - [{lt['category']}] {lt['key']}: {lt['value']}" for lt in long_term
            )
            parts.append(f"Текущая долгосрочная память:\n{items}\n")

        if parts:
            return "\n".join(parts) + "\n"
        return ""

    def _detect_working_category(self, key: str) -> str:
        """Определяет категорию рабочей памяти по ключу."""
        key_lower = key.lower()
        if any(w in key_lower for w in ("цель", "задач", "goal")):
            return "goal"
        if any(w in key_lower for w in ("ограничен", "требован", "constraint")):
            return "constraint"
        if any(w in key_lower for w in ("решен", "выбор", "decision")):
            return "decision"
        if any(w in key_lower for w in ("результат", "итог", "result")):
            return "result"
        return "fact"

    def _detect_long_term_category(self, key: str) -> str:
        """Определяет категорию долгосрочной памяти по ключу."""
        key_lower = key.lower()
        if any(w in key_lower for w in ("предпочт", "нрав", "стиль", "preference")):
            return "preference"
        if any(w in key_lower for w in ("решен", "выбор", "decision")):
            return "decision"
        return "knowledge"
