"""DI-провайдеры для модуля индексации."""

from functools import lru_cache

from app.modules.indexing.service import IndexingService


@lru_cache
def get_indexing_service() -> IndexingService:
    """Создаёт и кэширует IndexingService."""
    return IndexingService()
