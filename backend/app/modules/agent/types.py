"""Типы для агентной архитектуры.

Определяют контракт для реализации agent loop с поддержкой
вызова инструментов (function calling).
"""

from typing import Literal

from pydantic import BaseModel


class ToolCall(BaseModel):
    """Вызов инструмента агентом."""

    id: str
    name: str
    arguments: dict


class ToolResult(BaseModel):
    """Результат выполнения инструмента."""

    tool_call_id: str
    content: str
    is_error: bool = False


class AgentStep(BaseModel):
    """Один шаг агента: текст, вызов инструмента или результат.

    Используется для представления каждого шага в цикле агента.
    Тип шага определяет, какие поля заполнены.
    """

    type: Literal["content", "tool_call", "tool_result"]
    content: str | None = None
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
