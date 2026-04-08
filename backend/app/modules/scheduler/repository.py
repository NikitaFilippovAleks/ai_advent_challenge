"""Доступ к scheduler.db — чтение задач и запись результатов/сводок.

Используется SchedulerService внутри FastAPI-процесса.
MCP-сервер scheduler работает с той же БД через синхронный sqlite3.
"""

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

# Тот же путь, что и в scheduler_server.py
DB_PATH = Path(__file__).resolve().parents[3] / "data" / "scheduler.db"


class SchedulerRepository:
    """Async-репозиторий для scheduler.db."""

    @asynccontextmanager
    async def _connect(self):
        """Создаёт подключение с row_factory и foreign keys."""
        async with aiosqlite.connect(str(DB_PATH)) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA foreign_keys = ON")
            yield conn

    async def ensure_tables(self) -> None:
        """Создаёт таблицы при первом запуске (если scheduler_server ещё не создал БД)."""
        async with self._connect() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id TEXT PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    tool_name TEXT NOT NULL,
                    tool_args TEXT NOT NULL DEFAULT '{}',
                    cron_expression TEXT NOT NULL,
                    summary_cron TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS task_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES scheduled_tasks(id) ON DELETE CASCADE,
                    collected_at TEXT NOT NULL,
                    data TEXT NOT NULL
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS task_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES scheduled_tasks(id) ON DELETE CASCADE,
                    summary TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            await conn.commit()

    async def get_active_tasks(self) -> list[dict]:
        """Возвращает все задачи со статусом 'active'."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM scheduled_tasks WHERE status = 'active'"
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_all_tasks(self) -> list[dict]:
        """Возвращает все задачи (кроме cancelled) с количеством результатов."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM scheduled_tasks WHERE status != 'cancelled' ORDER BY created_at DESC"
            )
            rows = await cursor.fetchall()
            tasks = []
            for row in rows:
                task = dict(row)
                count_cursor = await conn.execute(
                    "SELECT COUNT(*) as cnt FROM task_results WHERE task_id = ?",
                    (task["id"],),
                )
                count_row = await count_cursor.fetchone()
                task["results_count"] = count_row["cnt"] if count_row else 0
                # Парсим tool_args из JSON
                task["tool_args"] = json.loads(task.get("tool_args", "{}"))
                tasks.append(task)
            return tasks

    async def get_task_by_id(self, task_id: str) -> dict | None:
        """Возвращает задачу по ID."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            task = dict(row)
            task["tool_args"] = json.loads(task.get("tool_args", "{}"))
            return task

    async def save_result(self, task_id: str, data: str) -> None:
        """Сохраняет результат сбора данных."""
        now = datetime.now(timezone.utc).isoformat()
        async with self._connect() as conn:
            await conn.execute(
                "INSERT INTO task_results (task_id, collected_at, data) VALUES (?, ?, ?)",
                (task_id, now, data),
            )
            await conn.commit()

    async def get_task_results(self, task_id: str, limit: int = 10) -> list[dict]:
        """Возвращает последние результаты сбора."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT collected_at, data FROM task_results WHERE task_id = ? ORDER BY collected_at DESC LIMIT ?",
                (task_id, limit),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_results_since(self, task_id: str, since: str) -> list[dict]:
        """Возвращает результаты сбора с указанного момента."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT collected_at, data FROM task_results WHERE task_id = ? AND collected_at > ? ORDER BY collected_at ASC",
                (task_id, since),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def save_summary(
        self, task_id: str, summary: str, period_start: str, period_end: str
    ) -> None:
        """Сохраняет сгенерированную сводку."""
        now = datetime.now(timezone.utc).isoformat()
        async with self._connect() as conn:
            await conn.execute(
                "INSERT INTO task_summaries (task_id, summary, period_start, period_end, created_at) VALUES (?, ?, ?, ?, ?)",
                (task_id, summary, period_start, period_end, now),
            )
            await conn.commit()

    async def get_last_summary(self, task_id: str) -> dict | None:
        """Возвращает последнюю сводку по задаче."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT summary, period_start, period_end, created_at FROM task_summaries WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
                (task_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_task_status(self, task_id: str, status: str) -> None:
        """Обновляет статус задачи."""
        now = datetime.now(timezone.utc).isoformat()
        async with self._connect() as conn:
            await conn.execute(
                "UPDATE scheduled_tasks SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, task_id),
            )
            await conn.commit()

    async def delete_task(self, task_id: str) -> None:
        """Удаляет задачу и все связанные данные (CASCADE)."""
        async with self._connect() as conn:
            await conn.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
            await conn.commit()
