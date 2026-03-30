"""Базовый класс для стратегий управления контекстом."""

from abc import ABC, abstractmethod


class BaseContextStrategy(ABC):
    """Интерфейс стратегии формирования контекста для LLM."""

    @abstractmethod
    async def build_context(self, conversation_id: str) -> list[dict]:
        """Формирует список сообщений для отправки в LLM.

        Returns:
            list[dict] с ключами: role (str), content (str)
        """
        ...
