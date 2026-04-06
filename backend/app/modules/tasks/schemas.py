"""Pydantic-схемы для модуля tasks."""

from pydantic import BaseModel, Field


class TaskOut(BaseModel):
    """Задача в ответе API."""

    id: str
    conversation_id: str
    phase: str
    previous_phase: str | None = None
    title: str
    steps: list[dict] | None = None
    current_step: int = 0
    status_text: str = ""
    created_at: str
    updated_at: str


class TransitionRequest(BaseModel):
    """Запрос на переход фазы."""

    phase: str


class PlanRequest(BaseModel):
    """Сохранение плана от LLM."""

    steps: list[dict] = Field(..., min_length=1)
