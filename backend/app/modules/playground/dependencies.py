"""Зависимости playground-модуля: синглтон LMStudioProvider + IndexingService для RAG."""

from functools import lru_cache

from app.modules.indexing.dependencies import get_indexing_service
from app.modules.indexing.service import IndexingService
from app.shared.llm.lmstudio import LMStudioProvider

__all__ = ["get_lmstudio_provider", "get_indexing_service_dep"]


@lru_cache
def get_lmstudio_provider() -> LMStudioProvider:
    """Возвращает закэшированный провайдер LM Studio."""
    return LMStudioProvider()


def get_indexing_service_dep() -> IndexingService:
    """Прокси к indexing.dependencies.get_indexing_service — единственное место
    кросс-модульного импорта для playground.
    """
    return get_indexing_service()
