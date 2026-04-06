"""Зависимости модуля tasks для FastAPI Depends."""

from functools import lru_cache

from app.modules.tasks.service import TaskService
from app.shared.llm.gigachat import GigaChatProvider


@lru_cache
def get_task_service() -> TaskService:
    """Создаёт и кэширует TaskService с GigaChatProvider."""
    llm = GigaChatProvider()
    return TaskService(llm=llm)
