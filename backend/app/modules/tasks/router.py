"""Роутер для управления задачами."""

from fastapi import APIRouter, Depends, HTTPException

from app.modules.tasks.dependencies import get_task_service
from app.modules.tasks.repository import get_active_task, get_task_history
from app.modules.tasks.schemas import PlanRequest, TaskOut, TransitionRequest
from app.modules.tasks.service import TaskService

router = APIRouter()


@router.get("/api/tasks/{conversation_id}/active", response_model=TaskOut | None)
async def get_active(conversation_id: str):
    """Возвращает активную задачу диалога или null."""
    return await get_active_task(conversation_id)


@router.put("/api/tasks/{task_id}/transition", response_model=TaskOut)
async def transition_phase(
    task_id: str,
    data: TransitionRequest,
    service: TaskService = Depends(get_task_service),
):
    """Переход фазы задачи."""
    try:
        return await service.transition(task_id, data.phase)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/api/tasks/{task_id}/plan", response_model=TaskOut)
async def save_plan(
    task_id: str,
    data: PlanRequest,
    service: TaskService = Depends(get_task_service),
):
    """Сохраняет план задачи."""
    return await service.save_plan(task_id, [s.copy() if isinstance(s, dict) else s for s in data.steps])


@router.get("/api/tasks/{conversation_id}/history", response_model=list[TaskOut])
async def history(conversation_id: str):
    """Все задачи диалога (включая завершённые)."""
    return await get_task_history(conversation_id)
