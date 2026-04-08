"""SchedulerService — фоновый планировщик задач.

Читает задачи из scheduler.db, регистрирует их в APScheduler.
По cron-расписанию вызывает MCPManager для сбора данных
и AgentRunner для генерации сводок через LLM.
"""

import json
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.modules.agent.mcp_manager import MCPManager
from app.modules.agent.runner import AgentRunner
from app.modules.scheduler.repository import SchedulerRepository

logger = logging.getLogger(__name__)

# Интервал синхронизации задач из БД (секунды)
SYNC_INTERVAL = 30


class SchedulerService:
    """Управляет фоновым выполнением задач по расписанию."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._repo = SchedulerRepository()
        self._mcp: MCPManager | None = None
        self._agent: AgentRunner | None = None
        # Какие задачи уже зарегистрированы в APScheduler: task_id → job_ids
        self._known_tasks: dict[str, list[str]] = {}

    async def start(self, mcp: MCPManager, agent: AgentRunner) -> None:
        """Запуск планировщика при старте FastAPI."""
        self._mcp = mcp
        self._agent = agent

        # Создаём таблицы при первом запуске (до MCP-сервера scheduler)
        await self._repo.ensure_tables()

        # Джоб для синхронизации задач из БД
        self._scheduler.add_job(
            self._sync_tasks,
            trigger=IntervalTrigger(seconds=SYNC_INTERVAL),
            id="__sync_tasks__",
            replace_existing=True,
        )

        self._scheduler.start()
        logger.info("SchedulerService запущен")

        # Первичная синхронизация
        await self._sync_tasks()

    async def stop(self) -> None:
        """Остановка планировщика при shutdown."""
        self._scheduler.shutdown(wait=False)
        logger.info("SchedulerService остановлен")

    async def trigger_summary(self, task_id: str) -> dict | None:
        """Ручная генерация сводки (вызывается из REST API)."""
        return await self._summarize(task_id)

    async def _sync_tasks(self) -> None:
        """Синхронизирует задачи из scheduler.db с APScheduler.

        Добавляет новые задачи, удаляет отменённые/паузнутые.
        """
        try:
            active_tasks = await self._repo.get_active_tasks()
            active_ids = {t["id"] for t in active_tasks}

            # Удаляем джобы для задач, которых больше нет (отменены/удалены)
            for task_id in list(self._known_tasks.keys()):
                if task_id not in active_ids:
                    for job_id in self._known_tasks[task_id]:
                        try:
                            self._scheduler.remove_job(job_id)
                        except Exception:
                            pass
                    del self._known_tasks[task_id]
                    logger.info("Удалены джобы для задачи %s", task_id)

            # Добавляем новые задачи
            for task in active_tasks:
                task_id = task["id"]
                if task_id in self._known_tasks:
                    continue

                job_ids = []
                cron_expr = task["cron_expression"]

                # Джоб сбора данных
                try:
                    trigger = self._parse_cron(cron_expr)
                    collect_job_id = f"collect_{task_id}"
                    tool_args = json.loads(task.get("tool_args", "{}"))
                    self._scheduler.add_job(
                        self._collect,
                        trigger=trigger,
                        id=collect_job_id,
                        replace_existing=True,
                        kwargs={
                            "task_id": task_id,
                            "tool_name": task["tool_name"],
                            "tool_args": tool_args,
                        },
                    )
                    job_ids.append(collect_job_id)
                    logger.info(
                        "Зарегистрирован сбор для '%s': %s → %s",
                        task["name"], cron_expr, task["tool_name"],
                    )
                except Exception as e:
                    logger.error("Ошибка регистрации сбора для '%s': %s", task["name"], e)

                # Джоб сводки (если указан summary_cron)
                summary_cron = task.get("summary_cron")
                if summary_cron:
                    try:
                        summary_trigger = self._parse_cron(summary_cron)
                        summary_job_id = f"summary_{task_id}"
                        self._scheduler.add_job(
                            self._summarize,
                            trigger=summary_trigger,
                            id=summary_job_id,
                            replace_existing=True,
                            kwargs={"task_id": task_id},
                        )
                        job_ids.append(summary_job_id)
                        logger.info(
                            "Зарегистрирована сводка для '%s': %s",
                            task["name"], summary_cron,
                        )
                    except Exception as e:
                        logger.error("Ошибка регистрации сводки для '%s': %s", task["name"], e)

                self._known_tasks[task_id] = job_ids

        except Exception as e:
            logger.error("Ошибка синхронизации задач: %s", e)

    async def _collect(self, task_id: str, tool_name: str, tool_args: dict) -> None:
        """Сбор данных: вызывает MCP-инструмент и сохраняет результат."""
        if not self._mcp:
            logger.warning("MCPManager не инициализирован")
            return

        try:
            result = await self._mcp.call_tool(tool_name, tool_args)
            await self._repo.save_result(task_id, result)
            logger.info("Собраны данные для задачи %s: %d символов", task_id, len(result))
        except Exception as e:
            # Сохраняем ошибку как результат — не останавливаем задачу
            error_data = json.dumps({"error": str(e)}, ensure_ascii=False)
            await self._repo.save_result(task_id, error_data)
            logger.error("Ошибка сбора для задачи %s: %s", task_id, e)

    async def _summarize(self, task_id: str) -> dict | None:
        """Генерация сводки: собирает результаты, вызывает LLM."""
        if not self._agent:
            logger.warning("AgentRunner не инициализирован")
            return None

        try:
            # Определяем период: с последней сводки до сейчас
            last_summary = await self._repo.get_last_summary(task_id)
            period_start = last_summary["created_at"] if last_summary else "1970-01-01T00:00:00+00:00"
            period_end = datetime.now(timezone.utc).isoformat()

            # Собираем результаты за период
            results = await self._repo.get_results_since(task_id, period_start)
            if not results:
                logger.info("Нет новых данных для сводки задачи %s", task_id)
                return None

            # Формируем текст с данными
            data_text = "\n\n".join(
                f"[{r['collected_at']}]\n{r['data']}" for r in results
            )

            # Получаем имя задачи для контекста
            task = await self._repo.get_task_by_id(task_id)
            task_name = task["name"] if task else task_id

            # Вызываем LLM для генерации сводки
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Ты аналитик. Составь краткую сводку на русском языке "
                        "по данным мониторинга. Выдели ключевые изменения, "
                        "тренды и важные события. Формат: 3-5 пунктов."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Задача мониторинга: {task_name}\n"
                        f"Период: {period_start} — {period_end}\n"
                        f"Количество сборов: {len(results)}\n\n"
                        f"Собранные данные:\n{data_text}"
                    ),
                },
            ]

            llm_result = await self._agent.run(messages)
            summary_text = llm_result.get("content", "Не удалось сгенерировать сводку")

            # Сохраняем сводку
            await self._repo.save_summary(task_id, summary_text, period_start, period_end)
            logger.info("Сводка для задачи %s сгенерирована: %d символов", task_id, len(summary_text))

            return {
                "summary": summary_text,
                "period_start": period_start,
                "period_end": period_end,
            }

        except Exception as e:
            logger.error("Ошибка генерации сводки для задачи %s: %s", task_id, e)
            return None

    @staticmethod
    def _parse_cron(cron_expr: str) -> CronTrigger:
        """Парсит cron-выражение (5 полей) в APScheduler CronTrigger."""
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Ожидается 5 полей cron, получено {len(parts)}: '{cron_expr}'")
        minute, hour, day, month, day_of_week = parts
        return CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
        )
