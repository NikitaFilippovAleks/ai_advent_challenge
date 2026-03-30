"""Зависимости модуля context для FastAPI Depends."""

from functools import lru_cache

from app.modules.context.service import ContextService
from app.shared.llm.gigachat import GigaChatProvider


@lru_cache
def get_context_service() -> ContextService:
    """Создаёт и кэширует ContextService с GigaChatProvider."""
    llm = GigaChatProvider()
    return ContextService(llm=llm)
