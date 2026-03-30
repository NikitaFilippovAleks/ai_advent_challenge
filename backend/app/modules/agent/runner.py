"""Раннер агента — оркестрирует цикл агента.

TODO: Реализовать agent loop:
1. Отправить сообщения в LLM с описанием инструментов
2. Если LLM возвращает tool_call — выполнить инструмент
3. Добавить результат в историю и повторить
4. Если LLM возвращает текст — вернуть как финальный ответ

Пока это заглушка — просто делегирует в LLM-провайдер.
"""

from collections.abc import AsyncGenerator

from app.modules.agent.tools import ToolRegistry
from app.shared.llm.base import BaseLLMProvider


class AgentRunner:
    """Оркестратор цикла агента с поддержкой инструментов."""

    def __init__(
        self,
        llm: BaseLLMProvider,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self._llm = llm
        self.tools = tool_registry or ToolRegistry()

    async def run_stream(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Запускает агента со стримингом.

        Пока просто делегирует в LLM-провайдер.
        В будущем здесь будет agent loop с вызовом инструментов.
        """
        async for event in self._llm.stream(
            messages, model=model, temperature=temperature
        ):
            yield event
