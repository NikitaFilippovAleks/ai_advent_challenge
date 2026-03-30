"""Реестр инструментов для агента.

Позволяет регистрировать callable-функции как инструменты,
которые агент может вызывать через function calling.
"""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class ToolDefinition:
    """Определение инструмента: функция + метаданные для LLM."""

    name: str
    description: str
    parameters: dict  # JSON Schema параметров
    fn: Callable


class ToolRegistry:
    """Реестр инструментов для агента."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        fn: Callable,
        description: str = "",
        parameters: dict | None = None,
    ) -> None:
        """Регистрирует инструмент в реестре."""
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters or {},
            fn=fn,
        )

    def get(self, name: str) -> ToolDefinition | None:
        """Возвращает инструмент по имени."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """Возвращает список имён зарегистрированных инструментов."""
        return list(self._tools.keys())

    def get_schemas(self) -> list[dict]:
        """Возвращает JSON-схемы всех инструментов для передачи в LLM."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in self._tools.values()
        ]
