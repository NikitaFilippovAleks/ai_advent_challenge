"""Зависимости playground-модуля: синглтоны LLM-провайдеров + IndexingService для RAG."""

from functools import lru_cache

from fastapi import HTTPException

from app.modules.indexing.dependencies import get_indexing_service
from app.modules.indexing.service import IndexingService
from app.shared.llm.base import BaseLLMProvider
from app.shared.llm.lmstudio import LMStudioProvider
from app.shared.llm.ollama import OllamaProvider

__all__ = [
    "get_lmstudio_provider",
    "get_ollama_provider",
    "get_provider",
    "get_indexing_service_dep",
]


@lru_cache
def get_lmstudio_provider() -> LMStudioProvider:
    """Возвращает закэшированный провайдер LM Studio."""
    return LMStudioProvider()


@lru_cache
def get_ollama_provider() -> OllamaProvider:
    """Возвращает закэшированный провайдер удалённого Ollama."""
    return OllamaProvider()


def get_provider(name: str) -> BaseLLMProvider:
    """Диспетчер LLM-провайдеров playground по строковому имени.

    Используется и роутером (для query/body-параметра), и теоретически
    через FastAPI Depends — но проще звать напрямую из обработчика.
    """
    if name == "lmstudio":
        return get_lmstudio_provider()
    if name == "ollama":
        return get_ollama_provider()
    raise HTTPException(status_code=400, detail=f"Неизвестный провайдер: {name}")


def get_indexing_service_dep() -> IndexingService:
    """Прокси к indexing.dependencies.get_indexing_service — единственное место
    кросс-модульного импорта для playground.
    """
    return get_indexing_service()
