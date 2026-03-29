"""Сервис управления контекстом диалога.

Поддерживает 4 стратегии:
1. summary — суммаризация старых сообщений (по умолчанию)
2. sliding_window — только последние N сообщений
3. sticky_facts — ключевые факты + последние N сообщений
4. branching — ветки диалога с чекпоинтами
"""

import json
import logging

from app.config import settings
from app.services.database import (
    add_summary,
    get_active_branch_id,
    get_branch_messages,
    get_facts,
    get_messages_with_ids,
    get_summaries,
    set_fact,
)
from app.services.gigachat_service import get_chat_response

logger = logging.getLogger(__name__)

# Маппинг ролей для читаемого форматирования
_ROLE_NAMES = {
    "user": "Пользователь",
    "assistant": "Ассистент",
    "system": "Система",
}


async def build_context(
    conversation_id: str, strategy: str = "summary"
) -> list[dict]:
    """Формирует список сообщений для отправки в LLM в зависимости от стратегии."""
    if strategy == "sliding_window":
        return await _build_sliding_window(conversation_id)
    elif strategy == "sticky_facts":
        return await _build_sticky_facts(conversation_id)
    elif strategy == "branching":
        return await _build_branch_context(conversation_id)
    else:
        # summary — дефолтная стратегия (существующая логика)
        return await _build_summary(conversation_id)


# --- Стратегия 1: Sliding Window ---


async def _build_sliding_window(conversation_id: str) -> list[dict]:
    """Скользящее окно: только последние N сообщений, остальное отбрасывается."""
    all_messages = await get_messages_with_ids(conversation_id)
    n = settings.context_recent_count
    recent = all_messages[-n:] if len(all_messages) > n else all_messages
    return [{"role": m["role"], "content": m["content"]} for m in recent]


# --- Стратегия 2: Sticky Facts ---


async def _build_sticky_facts(conversation_id: str) -> list[dict]:
    """Ключевые факты + последние N сообщений.

    Формирует системное сообщение с фактами, затем последние N сообщений.
    """
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
    conversation_id: str, user_text: str, assistant_text: str
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
                "Ключи — короткие названия на русском (цель, ограничения, предпочтения, решения и т.д.). "
                "Значения — краткие описания. "
                "Обнови существующие факты если информация изменилась, добавь новые если есть. "
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
        result = await get_chat_response(
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


# --- Стратегия 3: Branching ---


async def _build_branch_context(conversation_id: str) -> list[dict]:
    """Ветки диалога: берёт сообщения из активной ветки.

    Если активной ветки нет — возвращает все сообщения (как обычно).
    """
    branch_id = await get_active_branch_id(conversation_id)

    if branch_id is None:
        # Нет активной ветки — возвращаем все сообщения основной линии
        all_messages = await get_messages_with_ids(conversation_id)
        return [{"role": m["role"], "content": m["content"]} for m in all_messages]

    # Берём сообщения ветки (общие до чекпоинта + ветка)
    messages = await get_branch_messages(conversation_id, branch_id)
    return [{"role": m["role"], "content": m["content"]} for m in messages]


# --- Стратегия по умолчанию: Summary ---


async def _build_summary(conversation_id: str) -> list[dict]:
    """Суммаризация старых сообщений (существующая логика).

    Если сообщений мало — возвращает все как есть.
    Иначе: [системное сообщение с суммаризациями] + [последние N сообщений].
    """
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

        summary_text = await _summarize_block(block)
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


async def _summarize_block(messages: list[dict]) -> str:
    """Суммаризирует блок сообщений через GigaChat."""
    formatted = _format_messages_for_summary(messages)

    prompt_messages = [
        {
            "role": "system",
            "content": (
                "Кратко перескажи следующий фрагмент диалога между пользователем и ассистентом. "
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
        result = await get_chat_response(
            prompt_messages,
            model=settings.context_summary_model,
            temperature=0.3,
        )
        return result["content"]
    except Exception as e:
        logger.warning("Ошибка суммаризации, используем простое сокращение: %s", e)
        # Запасной вариант: просто берём первые слова каждого сообщения
        return _fallback_summary(messages)


def _format_messages_for_summary(messages: list[dict]) -> str:
    """Форматирует блок сообщений в читаемый текст для суммаризации."""
    lines = []
    for m in messages:
        role_name = _ROLE_NAMES.get(m["role"], m["role"])
        lines.append(f"{role_name}: {m['content']}")
    return "\n".join(lines)


def _fallback_summary(messages: list[dict]) -> str:
    """Запасная суммаризация если GigaChat недоступен — обрезка до первых 50 символов."""
    lines = []
    for m in messages:
        role_name = _ROLE_NAMES.get(m["role"], m["role"])
        content = m["content"][:50]
        if len(m["content"]) > 50:
            content += "..."
        lines.append(f"{role_name}: {content}")
    return "Фрагмент диалога: " + "; ".join(lines)
