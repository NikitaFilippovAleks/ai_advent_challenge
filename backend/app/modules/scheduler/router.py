"""REST API для управления задачами планировщика."""

from fastapi import APIRouter, Depends, HTTPException

from app.modules.scheduler.dependencies import (
    get_scheduler_repository,
    get_scheduler_service,
)
from app.modules.scheduler.repository import SchedulerRepository
from app.modules.scheduler.schemas import (
    ScheduledTaskOut,
    TaskResultOut,
    TaskSummaryOut,
)
from app.modules.scheduler.service import SchedulerService

router = APIRouter(tags=["scheduler"])


@router.get("/api/scheduler/tasks", response_model=list[ScheduledTaskOut])
async def list_tasks(
    repo: SchedulerRepository = Depends(get_scheduler_repository),
) -> list[dict]:
    """Возвращает все задачи планировщика."""
    return await repo.get_all_tasks()


@router.get("/api/scheduler/tasks/{task_id}/results", response_model=list[TaskResultOut])
async def get_task_results(
    task_id: str,
    limit: int = 10,
    repo: SchedulerRepository = Depends(get_scheduler_repository),
) -> list[dict]:
    """Возвращает последние результаты сбора по задаче."""
    task = await repo.get_task_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return await repo.get_task_results(task_id, limit)


@router.get("/api/scheduler/tasks/{task_id}/summary", response_model=TaskSummaryOut | None)
async def get_task_summary(
    task_id: str,
    repo: SchedulerRepository = Depends(get_scheduler_repository),
) -> dict | None:
    """Возвращает последнюю сводку по задаче."""
    task = await repo.get_task_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return await repo.get_last_summary(task_id)


@router.post("/api/scheduler/tasks/{task_id}/summarize", response_model=TaskSummaryOut | None)
async def trigger_summary(
    task_id: str,
    service: SchedulerService = Depends(get_scheduler_service),
    repo: SchedulerRepository = Depends(get_scheduler_repository),
) -> dict | None:
    """Ручная генерация сводки по задаче."""
    task = await repo.get_task_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    result = await service.trigger_summary(task_id)
    if not result:
        raise HTTPException(status_code=400, detail="Нет данных для сводки")
    return result


@router.put("/api/scheduler/tasks/{task_id}/pause")
async def pause_task(
    task_id: str,
    repo: SchedulerRepository = Depends(get_scheduler_repository),
) -> dict:
    """Ставит задачу на паузу."""
    task = await repo.get_task_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    await repo.update_task_status(task_id, "paused")
    return {"status": "paused"}


@router.put("/api/scheduler/tasks/{task_id}/resume")
async def resume_task(
    task_id: str,
    repo: SchedulerRepository = Depends(get_scheduler_repository),
) -> dict:
    """Возобновляет задачу."""
    task = await repo.get_task_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    await repo.update_task_status(task_id, "active")
    return {"status": "active"}


@router.delete("/api/scheduler/tasks/{task_id}")
async def delete_task(
    task_id: str,
    repo: SchedulerRepository = Depends(get_scheduler_repository),
) -> dict:
    """Удаляет задачу и все связанные данные."""
    task = await repo.get_task_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    await repo.delete_task(task_id)
    return {"status": "deleted"}
