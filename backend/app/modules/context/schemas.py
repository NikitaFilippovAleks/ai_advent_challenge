"""Pydantic-схемы для модуля context."""

from pydantic import BaseModel

# Допустимые стратегии контекста
VALID_STRATEGIES = {"summary", "sliding_window", "sticky_facts", "branching"}


class StrategyRequest(BaseModel):
    """Запрос на смену стратегии контекста."""

    strategy: str  # summary | sliding_window | sticky_facts | branching


class FactRequest(BaseModel):
    """Запрос на создание/обновление факта."""

    key: str
    value: str


class BranchRequest(BaseModel):
    """Запрос на создание ветки."""

    name: str
    checkpoint_message_id: int
