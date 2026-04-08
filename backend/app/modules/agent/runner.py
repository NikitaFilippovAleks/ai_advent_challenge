"""Раннер агента — оркестрирует цикл вызова LLM и инструментов.

Agent loop: LLM → function_call? → выполнить инструмент → повтор.
Если инструментов нет — делегирует в LLM напрямую (обратная совместимость).
"""

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
MAX_ITERATIONS = 10


class AgentRunner:
    """Оркестратор цикла агента с поддержкой MCP-инструментов."""

    def __init__(
        self,
        llm: BaseLLMProvider,
        mcp_manager: MCPManager | None = None,
    ) -> None:
        self._llm = llm
        self._mcp = mcp_manager

    async def run(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
    ) -> dict:
        """Запускает агента (без стриминга). Возвращает финальный ответ.

        Returns:
            dict с ключами: content, usage, tool_calls (список вызовов)
        """
        # Получаем инструменты из MCP
        tool_schemas = self._mcp.get_all_tool_schemas() if self._mcp else []
        gigachat_functions = mcp_schemas_to_gigachat_functions(tool_schemas) if tool_schemas else None

        # Без инструментов — обычный вызов LLM
        if not gigachat_functions:
            return await self._llm.chat(messages, model=model, temperature=temperature)

        # Agent loop
        work_messages = list(messages)
        tool_calls_log = []

        for iteration in range(MAX_ITERATIONS):
            result = await self._llm.chat(
                work_messages, model=model, temperature=temperature,
                functions=gigachat_functions,
            )

            # Если LLM вернул function_call — выполняем инструмент
            if result.get("function_call"):
                fc = result["function_call"]
                name, arguments = fc["name"], fc["arguments"]

                logger.info("Agent loop [%d]: вызов %s(%s)", iteration, name, arguments)

                # Выполняем инструмент через MCP
                tool_result = await self._mcp.call_tool(name, arguments)

                tool_calls_log.append({
                    "name": name,
                    "arguments": arguments,
                    "result": tool_result,
                })

                # Добавляем в историю для следующей итерации
                work_messages.append(build_function_call_message(name, arguments))
                work_messages.append(build_function_result_message(name, tool_result))
                continue

            # Текстовый ответ — завершаем цикл
            result["tool_calls"] = tool_calls_log
            return result

        # Превышен лимит итераций
        return {
            "content": "Превышен лимит вызовов инструментов. Попробуйте переформулировать запрос.",
            "usage": None,
            "tool_calls": tool_calls_log,
        }

    async def run_stream(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Запускает агента со стримингом SSE-событий.

        Генерирует события:
        - {"type": "delta", "data": {"content": "...", "type": "content"}}
        - {"type": "tool_call", "data": {"name": "...", "arguments": {...}}}
        - {"type": "tool_result", "data": {"name": "...", "content": "..."}}
        - {"type": "usage", "data": {...}}
        - {"type": "done", "data": {}}
        """
        # Получаем инструменты из MCP
        tool_schemas = self._mcp.get_all_tool_schemas() if self._mcp else []
        gigachat_functions = mcp_schemas_to_gigachat_functions(tool_schemas) if tool_schemas else None

        # Без инструментов — обычный стриминг через LLM
        if not gigachat_functions:
            async for event in self._llm.stream(
                messages, model=model, temperature=temperature
            ):
                yield event
            return

        # Agent loop (не стримим промежуточные вызовы LLM, стримим только tool events)
        work_messages = list(messages)

        for iteration in range(MAX_ITERATIONS):
            result = await self._llm.chat(
                work_messages, model=model, temperature=temperature,
                functions=gigachat_functions,
            )

            # Если LLM вернул function_call — выполняем инструмент
            if result.get("function_call"):
                fc = result["function_call"]
                name, arguments = fc["name"], fc["arguments"]

                logger.info("Agent loop [%d]: вызов %s(%s)", iteration, name, arguments)

                # Отправляем событие о вызове инструмента
                yield {
                    "type": "tool_call",
                    "data": {"name": name, "arguments": arguments},
                }

                # Выполняем инструмент через MCP
                tool_result = await self._mcp.call_tool(name, arguments)

                # Отправляем результат
                yield {
                    "type": "tool_result",
                    "data": {"name": name, "content": tool_result},
                }

                # Добавляем в историю для следующей итерации
                work_messages.append(build_function_call_message(name, arguments))
                work_messages.append(build_function_result_message(name, tool_result))
                continue

            # Текстовый ответ — отправляем как delta + done
            content = result.get("content", "")
            if content:
                yield {
                    "type": "delta",
                    "data": {"content": content, "type": "content"},
                }
            if result.get("usage"):
                yield {"type": "usage", "data": result["usage"]}
            yield {"type": "done", "data": {}}
            return

        # Превышен лимит итераций
        yield {
            "type": "delta",
            "data": {
                "content": "Превышен лимит вызовов инструментов. Попробуйте переформулировать запрос.",
                "type": "content",
            },
        }
        yield {"type": "done", "data": {}}
