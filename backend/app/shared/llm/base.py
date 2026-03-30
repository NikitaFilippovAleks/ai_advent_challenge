"""Абстрактный базовый класс для LLM-провайдеров.

Определяет контракт, которому должен соответствовать любой LLM-провайдер.
Модули зависят от этого интерфейса, а не от конкретной реализации.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator


class BaseLLMProvider(ABC):
    """Базовый интерфейс для работы с языковой моделью."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
    ) -> dict:
        """Отправляет сообщения и возвращает полный ответ.

        Returns:
            dict с ключами: content (str), usage (dict | None)
        """
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Стримит ответ чанками через async-генератор.

        Yields:
            dict с ключами: type ("delta" | "usage" | "done"), data (dict)
        """
        ...

    @abstractmethod
    async def list_models(self) -> list[dict]:
        """Возвращает список доступных моделей.

        Returns:
            list[dict] с ключами: id (str), name (str)
        """
        ...
