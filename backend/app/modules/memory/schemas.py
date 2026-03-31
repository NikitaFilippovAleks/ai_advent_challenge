"""Pydantic-схемы для модуля memory."""

from pydantic import BaseModel


class InsightRequest(BaseModel):
    """Запрос на добавление краткосрочного наблюдения."""

    content: str


class WorkingMemoryRequest(BaseModel):
    """Запрос на создание/обновление записи рабочей памяти."""

    key: str
    value: str
    category: str = "fact"  # goal, constraint, decision, result, fact


class LongTermMemoryRequest(BaseModel):
    """Запрос на создание/обновление записи долгосрочной памяти."""

    key: str
    value: str
    category: str  # preference, knowledge, decision
