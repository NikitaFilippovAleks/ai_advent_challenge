"""Раннер агента — оркестрирует цикл агента.

TODO: Реализовать agent loop:
1. Отправить сообщения в LLM с описанием инструментов
2. Если LLM возвращает tool_call — выполнить инструмент
3. Добавить результат в историю и повторить
4. Если LLM возвращает текст — вернуть как финальный ответ

Пока это заглушка — просто делегирует в chat_service.
"""

from collections.abc import AsyncGenerator

from app.services.agent.tools import ToolRegistry
from app.services.gigachat_service import stream_chat_response


class AgentRunner:
    """Оркестратор цикла агента с поддержкой инструментов."""

    def __init__(self, tool_registry: ToolRegistry | None = None) -> None:
        self.tools = tool_registry or ToolRegistry()

    async def run_stream(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Запускает агента со стримингом.

        Пока просто делегирует в stream_chat_response.
        В будущем здесь будет agent loop с вызовом инструментов.
        """
        async for event in stream_chat_response(messages, model=model, temperature=temperature):
            yield event
