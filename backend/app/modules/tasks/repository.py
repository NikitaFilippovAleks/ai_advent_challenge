"""Репозиторий для CRUD-операций с задачами."""

import json
import uuid

from sqlalchemy import select

from app.core.database import _now_iso, async_session
from app.models import Task


async def create_task(conversation_id: str, title: str) -> dict:
    """Создаёт задачу в фазе planning."""
    now = _now_iso()
    task = Task(
        id=str(uuid.uuid4()),
        conversation_id=conversation_id,
        phase="planning",
        title=title,
        status_text="Планирование: составляю план",
        created_at=now,
        updated_at=now,
    )
    async with async_session() as session:
        session.add(task)
        await session.commit()
    return _task_to_dict(task)


async def get_active_task(conversation_id: str) -> dict | None:
    """Возвращает активную задачу диалога (phase не done/cancelled) или None."""
    async with async_session() as session:
        result = await session.execute(
            select(Task)
            .where(Task.conversation_id == conversation_id)
            .where(Task.phase.notin_(["done", "cancelled"]))
            .order_by(Task.created_at.desc())
            .limit(1)
        )
        task = result.scalar_one_or_none()
    if task is None:
        return None
    return _task_to_dict(task)


async def get_task(task_id: str) -> dict | None:
    """Возвращает задачу по ID."""
    async with async_session() as session:
        task = await session.get(Task, task_id)
    if task is None:
        return None
    return _task_to_dict(task)


async def update_task(task_id: str, **fields) -> dict | None:
    """Обновляет поля задачи."""
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if task is None:
            return None
        for key, value in fields.items():
            if value is not None:
                setattr(task, key, value)
        task.updated_at = _now_iso()
        await session.commit()
        await session.refresh(task)
    return _task_to_dict(task)


async def get_task_history(conversation_id: str) -> list[dict]:
    """Возвращает все задачи диалога (включая завершённые)."""
    async with async_session() as session:
        result = await session.execute(
            select(Task)
            .where(Task.conversation_id == conversation_id)
            .order_by(Task.created_at.desc())
        )
        tasks = result.scalars().all()
    return [_task_to_dict(t) for t in tasks]


def _task_to_dict(task: Task) -> dict:
    """Конвертирует ORM-объект в словарь."""
    steps = None
    if task.plan_json:
        steps = json.loads(task.plan_json)
    return {
        "id": task.id,
        "conversation_id": task.conversation_id,
        "phase": task.phase,
        "previous_phase": task.previous_phase,
        "title": task.title,
        "steps": steps,
        "current_step": task.current_step,
        "status_text": task.status_text,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }
