"""Зависимости модуля scheduler для FastAPI Depends."""

from functools import lru_cache

from app.modules.scheduler.repository import SchedulerRepository
from app.modules.scheduler.service import SchedulerService


@lru_cache
def get_scheduler_repository() -> SchedulerRepository:
    """Создаёт и кэширует singleton SchedulerRepository."""
    return SchedulerRepository()


@lru_cache
def get_scheduler_service() -> SchedulerService:
    """Создаёт и кэширует singleton SchedulerService."""
    return SchedulerService()
