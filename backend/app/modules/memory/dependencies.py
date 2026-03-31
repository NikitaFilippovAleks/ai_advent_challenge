"""DI-фабрика для модуля memory."""

from functools import lru_cache

from app.modules.memory.service import MemoryService
from app.shared.llm.gigachat import GigaChatProvider


@lru_cache
def get_memory_service() -> MemoryService:
    """Создаёт и кэширует синглтон MemoryService."""
    llm = GigaChatProvider()
    return MemoryService(llm=llm)
