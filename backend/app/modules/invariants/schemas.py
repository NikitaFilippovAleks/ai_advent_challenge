"""Pydantic-схемы для инвариантов."""

from typing import Literal

from pydantic import BaseModel, Field


# Допустимые категории инвариантов
InvariantCategoryType = Literal["architecture", "technical", "stack", "business"]


class InvariantCreate(BaseModel):
    """Создание инварианта."""
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    category: InvariantCategoryType = "business"
    is_active: bool = True
    priority: int = Field(default=0, ge=0)


class InvariantUpdate(BaseModel):
    """Обновление инварианта (частичное)."""
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, min_length=1, max_length=5000)
    category: InvariantCategoryType | None = None
    is_active: bool | None = None
    priority: int | None = Field(None, ge=0)


class InvariantOut(BaseModel):
    """Инвариант в ответе API."""
    id: str
    name: str
    description: str
    category: str
    is_active: bool
    priority: int
    created_at: str
    updated_at: str
