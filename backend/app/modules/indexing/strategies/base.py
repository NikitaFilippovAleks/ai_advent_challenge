"""Базовый класс для стратегий разбиения текста на чанки."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ChunkResult:
    """Результат разбиения — один чанк текста с метаданными."""

    content: str
    chunk_index: int
    section: str | None
    char_start: int
    char_end: int


class BaseChunkingStrategy(ABC):
    """Интерфейс стратегии разбиения текста на чанки."""

    @abstractmethod
    def chunk(self, text: str, source: str) -> list[ChunkResult]:
        """Разбивает текст на чанки с метаданными.

        Args:
            text: исходный текст документа
            source: путь к файлу-источнику

        Returns:
            список чанков с позициями и секциями
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Имя стратегии для хранения в БД."""
        ...
