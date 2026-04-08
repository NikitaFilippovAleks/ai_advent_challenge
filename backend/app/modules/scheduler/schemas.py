"""Pydantic-схемы для Scheduler API."""

from pydantic import BaseModel


class ScheduledTaskOut(BaseModel):
    """Задача планировщика для ответа API."""

    id: str
    name: str
    tool_name: str
    tool_args: dict
    cron_expression: str
    summary_cron: str | None
    status: str
    results_count: int = 0
    created_at: str


class TaskResultOut(BaseModel):
    """Результат сбора данных."""

    collected_at: str
    data: str


class TaskSummaryOut(BaseModel):
    """Сгенерированная сводка."""

    summary: str
    period_start: str
    period_end: str
    created_at: str
