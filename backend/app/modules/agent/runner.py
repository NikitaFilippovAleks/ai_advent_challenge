"""Раннер агента — оркестрирует цикл вызова LLM и инструментов.

Agent loop: LLM → function_call? → выполнить инструмент → повтор.
Если инструментов нет — делегирует в LLM напрямую (обратная совместимость).
"""

import json
import logging
from collections.abc import AsyncGenerator

from app.modules.agent.gigachat_adapter import (
    build_function_call_message,
    build_function_result_message,
    mcp_schemas_to_gigachat_functions,
)
from app.modules.agent.mcp_manager import MCPManager
from app.shared.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

# Максимум итераций agent loop (защита от бесконечного цикла)
MAX_ITERATIONS = 15

# Максимум повторных вызовов одного и того же инструмента с теми же аргументами
MAX_SAME_CALL_REPEATS = 1

# Если LLM вернул текст короче этого порога и ещё есть итерации —
# считаем что он остановился преждевременно и просим продолжить
MIN_FINAL_RESPONSE_LENGTH = 80

# Сколько раз можно попросить LLM продолжить после короткого ответа
MAX_CONTINUATION_NUDGES = 3

# Модели GigaChat, поддерживающие function calling
_FUNCTION_CAPABLE_MODELS = {"GigaChat-Pro", "GigaChat-2-Pro"}

# Контекст окружения для подсказки LLM
_ENV_CONTEXT = (
    "Контекст окружения: рабочая директория /app, "
    "git-репозиторий проекта смонтирован в /repo. "
    "Для git-операций используй repo_path=/repo. "
    "Для поиска файлов проекта используй directory=/app."
)


class AgentRunner:
    """Оркестратор цикла агента с поддержкой MCP-инструментов."""

    def __init__(
        self,
        llm: BaseLLMProvider,
        mcp_manager: MCPManager | None = None,
    ) -> None:
        self._llm = llm
        self._mcp = mcp_manager

    def _build_tools_system_content(self, tool_schemas: list[dict]) -> str:
        """Формирует текст system-промпта с описанием доступных инструментов."""
        tool_lines = []
        for schema in tool_schemas:
            tool_lines.append(f"- {schema['name']}: {schema.get('description', '')}")
        tools_list = "\n".join(tool_lines)

        return (
            "У тебя есть доступ к инструментам (functions). "
            "ОБЯЗАТЕЛЬНО используй function_call для выполнения действий. "
            "НЕ пиши код, НЕ показывай примеры кода — вызывай инструменты напрямую.\n\n"
            f"Доступные инструменты:\n{tools_list}\n\n"
            f"{_ENV_CONTEXT}\n\n"
            "ПРАВИЛА:\n"
            "1. Вызывай инструменты последовательно через function_call.\n"
            "2. НЕ повторяй вызов инструмента, если уже получил от него результат.\n"
            "3. После получения результата ПЕРЕХОДИ к следующему шагу запроса.\n"
            "4. Выполни ВСЕ части запроса пользователя, не останавливайся на середине.\n"
            "5. Когда ВСЕ данные собраны — сформируй подробный финальный ответ.\n"
            "6. НЕ описывай что ты собираешься делать — просто вызывай function_call."
        )

    def _inject_tools_prompt(self, messages: list[dict], tool_schemas: list[dict]) -> list[dict]:
        """Добавляет system-промпт об инструментах и объединяет все system-сообщения в одно.

        GigaChat API требует ровно одно system-сообщение первым.
        """
        tools_content = self._build_tools_system_content(tool_schemas)

        system_parts = []
        other_messages = []
        for m in messages:
            if m["role"] == "system":
                system_parts.append(m["content"])
            else:
                other_messages.append(m)

        system_parts.append(tools_content)

        merged_system = {"role": "system", "content": "\n\n".join(system_parts)}
        return [merged_system] + other_messages

    def _make_call_key(self, name: str, arguments: dict) -> str:
        """Создаёт ключ для обнаружения повторных вызовов."""
        return f"{name}::{json.dumps(arguments, sort_keys=True, ensure_ascii=False)}"

    def _handle_duplicate_call(
        self, work_messages: list[dict], name: str, arguments: dict, iteration: int
    ) -> None:
        """Обрабатывает повторный вызов инструмента — вставляет подсказку вместо реального вызова."""
        logger.warning("Agent loop [%d]: повторный вызов %s — пропускаем", iteration, name)
        work_messages.append(build_function_call_message(name, arguments))
        work_messages.append(build_function_result_message(
            name,
            "Этот инструмент уже был вызван ранее. "
            "Используй полученный результат. Переходи к СЛЕДУЮЩЕМУ шагу.",
        ))

    def _build_continuation_message(self, tool_calls_log: list[dict]) -> dict:
        """Формирует сообщение-напоминание продолжить выполнение."""
        called = ", ".join(tc["name"] for tc in tool_calls_log)
        return {
            "role": "user",
            "content": (
                f"Ты уже вызвал: {called}. "
                "Но запрос пользователя ещё не выполнен полностью. "
                "Продолжай вызывать function_call для оставшихся шагов. "
                "Не описывай — вызывай."
            ),
        }

    async def run(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
    ) -> dict:
        """Запускает агента (без стриминга). Возвращает финальный ответ."""
        tool_schemas = self._mcp.get_all_tool_schemas() if self._mcp else []
        gigachat_functions = mcp_schemas_to_gigachat_functions(tool_schemas) if tool_schemas else None

        if not gigachat_functions:
            return await self._llm.chat(messages, model=model, temperature=temperature)

        if model and model not in _FUNCTION_CAPABLE_MODELS:
            logger.warning(
                "Модель '%s' может не поддерживать function calling. "
                "Рекомендуется: %s", model, ", ".join(_FUNCTION_CAPABLE_MODELS),
            )

        work_messages = self._inject_tools_prompt(messages, tool_schemas)
        tool_calls_log = []
        call_counts: dict[str, int] = {}
        nudge_count = 0

        for iteration in range(MAX_ITERATIONS):
            result = await self._llm.chat(
                work_messages, model=model, temperature=temperature,
                functions=gigachat_functions,
            )

            if result.get("function_call"):
                fc = result["function_call"]
                name, arguments = fc["name"], fc["arguments"]

                call_key = self._make_call_key(name, arguments)
                call_counts[call_key] = call_counts.get(call_key, 0) + 1

                if call_counts[call_key] > MAX_SAME_CALL_REPEATS:
                    self._handle_duplicate_call(work_messages, name, arguments, iteration)
                    continue

                logger.info("Agent loop [%d]: вызов %s(%s)", iteration, name, arguments)
                tool_result = await self._mcp.call_tool(name, arguments)

                tool_calls_log.append({
                    "name": name, "arguments": arguments, "result": tool_result,
                })

                work_messages.append(build_function_call_message(name, arguments))
                work_messages.append(build_function_result_message(name, tool_result))
                continue

            # Текстовый ответ — проверяем не остановился ли LLM преждевременно
            content = result.get("content", "")

            if (
                len(content.strip()) < MIN_FINAL_RESPONSE_LENGTH
                and tool_calls_log
                and nudge_count < MAX_CONTINUATION_NUDGES
            ):
                logger.info(
                    "Agent loop [%d]: короткий ответ (%d символов), "
                    "отправляем напоминание продолжить", iteration, len(content),
                )
                if content.strip():
                    work_messages.append({"role": "assistant", "content": content})
                work_messages.append(self._build_continuation_message(tool_calls_log))
                nudge_count += 1
                continue

            result["tool_calls"] = tool_calls_log
            return result

        # Превышен лимит — возвращаем сводку
        return self._build_fallback_response(tool_calls_log)

    async def run_stream(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Запускает агента со стримингом SSE-событий."""
        tool_schemas = self._mcp.get_all_tool_schemas() if self._mcp else []
        gigachat_functions = mcp_schemas_to_gigachat_functions(tool_schemas) if tool_schemas else None

        if not gigachat_functions:
            async for event in self._llm.stream(
                messages, model=model, temperature=temperature
            ):
                yield event
            return

        if model and model not in _FUNCTION_CAPABLE_MODELS:
            logger.warning(
                "Модель '%s' может не поддерживать function calling. "
                "Рекомендуется: %s", model, ", ".join(_FUNCTION_CAPABLE_MODELS),
            )

        work_messages = self._inject_tools_prompt(messages, tool_schemas)
        tool_calls_log = []
        call_counts: dict[str, int] = {}
        nudge_count = 0

        for iteration in range(MAX_ITERATIONS):
            result = await self._llm.chat(
                work_messages, model=model, temperature=temperature,
                functions=gigachat_functions,
            )

            if result.get("function_call"):
                fc = result["function_call"]
                name, arguments = fc["name"], fc["arguments"]

                call_key = self._make_call_key(name, arguments)
                call_counts[call_key] = call_counts.get(call_key, 0) + 1

                if call_counts[call_key] > MAX_SAME_CALL_REPEATS:
                    self._handle_duplicate_call(work_messages, name, arguments, iteration)
                    continue

                logger.info("Agent loop [%d]: вызов %s(%s)", iteration, name, arguments)

                yield {
                    "type": "tool_call",
                    "data": {"name": name, "arguments": arguments},
                }

                tool_result = await self._mcp.call_tool(name, arguments)

                tool_calls_log.append({
                    "name": name, "arguments": arguments, "result": tool_result,
                })

                yield {
                    "type": "tool_result",
                    "data": {"name": name, "content": tool_result},
                }

                work_messages.append(build_function_call_message(name, arguments))
                work_messages.append(build_function_result_message(name, tool_result))
                continue

            # Текстовый ответ — проверяем не остановился ли LLM преждевременно
            content = result.get("content", "")

            if (
                len(content.strip()) < MIN_FINAL_RESPONSE_LENGTH
                and tool_calls_log
                and nudge_count < MAX_CONTINUATION_NUDGES
            ):
                logger.info(
                    "Agent loop [%d]: короткий ответ (%d символов), "
                    "отправляем напоминание продолжить", iteration, len(content),
                )
                if content.strip():
                    work_messages.append({"role": "assistant", "content": content})
                work_messages.append(self._build_continuation_message(tool_calls_log))
                nudge_count += 1
                continue

            # Финальный ответ
            if content:
                yield {
                    "type": "delta",
                    "data": {"content": content, "type": "content"},
                }
            if result.get("usage"):
                yield {"type": "usage", "data": result["usage"]}
            yield {"type": "done", "data": {}}
            return

        # Превышен лимит — формируем сводку
        fallback = self._build_fallback_response(tool_calls_log)
        yield {
            "type": "delta",
            "data": {"content": fallback["content"], "type": "content"},
        }
        yield {"type": "done", "data": {}}

    def _build_fallback_response(self, tool_calls_log: list[dict]) -> dict:
        """Формирует ответ из собранных результатов при превышении лимита."""
        if not tool_calls_log:
            return {
                "content": "Превышен лимит вызовов инструментов.",
                "usage": None,
                "tool_calls": [],
            }

        summary_parts = []
        for tc in tool_calls_log:
            summary_parts.append(f"**{tc['name']}**: {tc['result'][:300]}")

        return {
            "content": (
                "Собраны результаты инструментов:\n\n"
                + "\n\n".join(summary_parts)
            ),
            "usage": None,
            "tool_calls": tool_calls_log,
        }
