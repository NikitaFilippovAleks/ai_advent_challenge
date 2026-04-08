"""Scheduler MCP-сервер — управляет задачами с периодическим выполнением.

Запускается как subprocess через stdio-транспорт.
Инструменты: create_scheduled_task, list_scheduled_tasks,
get_task_results, get_task_summary, cancel_scheduled_task.
"""

import asyncio
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from croniter import croniter
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

server = Server("scheduler-server")

# БД рядом с mcp_servers.json
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "scheduler.db"


def _get_db() -> sqlite3.Connection:
    """Создаёт подключение к SQLite и таблицы при необходимости."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES scheduled_tasks(id) ON DELETE CASCADE,
            collected_at TEXT NOT NULL,
            data TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES scheduled_tasks(id) ON DELETE CASCADE,
            summary TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Возвращает список доступных инструментов."""
    return [
        Tool(
            name="create_scheduled_task",
            description=(
                "Создаёт задачу с периодическим выполнением MCP-инструмента по cron-расписанию. "
                "Результаты накапливаются, по отдельному расписанию генерируется сводка через LLM."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Уникальное имя задачи (например, 'git-monitor')",
                    },
                    "tool_name": {
                        "type": "string",
                        "description": "Имя MCP-инструмента для вызова (например, 'git_log')",
                    },
                    "tool_args_repo_path": {
                        "type": "string",
                        "description": "Путь к репозиторию (аргумент repo_path для git-инструментов, например '/app')",
                    },
                    "tool_args_max_count": {
                        "type": "integer",
                        "description": "Максимальное количество записей (аргумент max_count, по умолчанию 10)",
                    },
                    "cron_expression": {
                        "type": "string",
                        "description": "Cron-расписание сбора данных (например, '*/2 * * * *' — каждые 2 минуты)",
                    },
                    "summary_cron": {
                        "type": "string",
                        "description": "Cron-расписание генерации сводки (например, '0 18 * * *' — каждый день в 18:00). Опционально.",
                    },
                },
                "required": ["name", "tool_name", "tool_args_repo_path", "cron_expression"],
            },
        ),
        Tool(
            name="list_scheduled_tasks",
            description="Показывает все активные и приостановленные задачи планировщика.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_task_results",
            description="Возвращает последние результаты сбора данных по задаче.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_name": {
                        "type": "string",
                        "description": "Имя задачи",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Максимальное количество результатов (по умолчанию 10)",
                        "default": 10,
                    },
                },
                "required": ["task_name"],
            },
        ),
        Tool(
            name="get_task_summary",
            description="Возвращает последнюю сгенерированную сводку по задаче.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_name": {
                        "type": "string",
                        "description": "Имя задачи",
                    },
                },
                "required": ["task_name"],
            },
        ),
        Tool(
            name="cancel_scheduled_task",
            description="Отменяет задачу планировщика (прекращает сбор данных).",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_name": {
                        "type": "string",
                        "description": "Имя задачи для отмены",
                    },
                },
                "required": ["task_name"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Выполняет вызов инструмента."""
    db = _get_db()
    try:
        if name == "create_scheduled_task":
            result = _create_task(db, arguments)
        elif name == "list_scheduled_tasks":
            result = _list_tasks(db)
        elif name == "get_task_results":
            result = _get_results(db, arguments)
        elif name == "get_task_summary":
            result = _get_summary(db, arguments)
        elif name == "cancel_scheduled_task":
            result = _cancel_task(db, arguments)
        else:
            result = f"Неизвестный инструмент: {name}"
    finally:
        db.close()

    return [TextContent(type="text", text=result)]


def _create_task(db: sqlite3.Connection, args: dict) -> str:
    """Создаёт новую задачу."""
    task_name = args.get("name", "")
    tool_name = args.get("tool_name", "")
    cron_expr = args.get("cron_expression", "")
    summary_cron = args.get("summary_cron")

    # Собираем tool_args из плоских параметров tool_args_*
    tool_args = {}
    for key, value in args.items():
        if key.startswith("tool_args_") and value is not None:
            arg_name = key[len("tool_args_"):]  # "tool_args_repo_path" → "repo_path"
            tool_args[arg_name] = value

    if not task_name or not tool_name or not cron_expr:
        return "Ошибка: name, tool_name и cron_expression обязательны"

    # Валидация cron-выражения
    if not croniter.is_valid(cron_expr):
        return f"Ошибка: невалидное cron-выражение '{cron_expr}'"
    if summary_cron and not croniter.is_valid(summary_cron):
        return f"Ошибка: невалидное cron-выражение для сводки '{summary_cron}'"

    # Проверка уникальности имени
    existing = db.execute(
        "SELECT id FROM scheduled_tasks WHERE name = ?", (task_name,)
    ).fetchone()
    if existing:
        return f"Ошибка: задача с именем '{task_name}' уже существует"

    task_id = str(uuid.uuid4())
    now = _now_iso()
    db.execute(
        """INSERT INTO scheduled_tasks
           (id, name, tool_name, tool_args, cron_expression, summary_cron, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
        (task_id, task_name, tool_name, json.dumps(tool_args), cron_expr, summary_cron, now, now),
    )
    db.commit()

    result = {
        "id": task_id,
        "name": task_name,
        "status": "active",
        "cron_expression": cron_expr,
        "tool_name": tool_name,
    }
    if summary_cron:
        result["summary_cron"] = summary_cron
    return json.dumps(result, ensure_ascii=False)


def _list_tasks(db: sqlite3.Connection) -> str:
    """Список всех задач (кроме отменённых)."""
    rows = db.execute(
        "SELECT * FROM scheduled_tasks WHERE status != 'cancelled' ORDER BY created_at DESC"
    ).fetchall()
    tasks = []
    for row in rows:
        count = db.execute(
            "SELECT COUNT(*) as cnt FROM task_results WHERE task_id = ?", (row["id"],)
        ).fetchone()["cnt"]
        tasks.append({
            "id": row["id"],
            "name": row["name"],
            "tool_name": row["tool_name"],
            "cron_expression": row["cron_expression"],
            "summary_cron": row["summary_cron"],
            "status": row["status"],
            "results_count": count,
            "created_at": row["created_at"],
        })
    return json.dumps(tasks, ensure_ascii=False) if tasks else "Нет активных задач"


def _get_results(db: sqlite3.Connection, args: dict) -> str:
    """Последние результаты сбора по имени задачи."""
    task_name = args.get("task_name", "")
    limit = args.get("limit", 10)

    task = db.execute(
        "SELECT id FROM scheduled_tasks WHERE name = ?", (task_name,)
    ).fetchone()
    if not task:
        return f"Задача '{task_name}' не найдена"

    rows = db.execute(
        "SELECT collected_at, data FROM task_results WHERE task_id = ? ORDER BY collected_at DESC LIMIT ?",
        (task["id"], limit),
    ).fetchall()

    if not rows:
        return f"Результатов для задачи '{task_name}' пока нет"

    results = [{"collected_at": r["collected_at"], "data": r["data"]} for r in rows]
    return json.dumps(results, ensure_ascii=False)


def _get_summary(db: sqlite3.Connection, args: dict) -> str:
    """Последняя сводка по имени задачи."""
    task_name = args.get("task_name", "")

    task = db.execute(
        "SELECT id FROM scheduled_tasks WHERE name = ?", (task_name,)
    ).fetchone()
    if not task:
        return f"Задача '{task_name}' не найдена"

    row = db.execute(
        "SELECT summary, period_start, period_end, created_at FROM task_summaries WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
        (task["id"],),
    ).fetchone()

    if not row:
        return f"Сводок для задачи '{task_name}' пока нет"

    return json.dumps({
        "summary": row["summary"],
        "period_start": row["period_start"],
        "period_end": row["period_end"],
        "created_at": row["created_at"],
    }, ensure_ascii=False)


def _cancel_task(db: sqlite3.Connection, args: dict) -> str:
    """Отменяет задачу."""
    task_name = args.get("task_name", "")

    task = db.execute(
        "SELECT id, status FROM scheduled_tasks WHERE name = ?", (task_name,)
    ).fetchone()
    if not task:
        return f"Задача '{task_name}' не найдена"
    if task["status"] == "cancelled":
        return f"Задача '{task_name}' уже отменена"

    now = _now_iso()
    db.execute(
        "UPDATE scheduled_tasks SET status = 'cancelled', updated_at = ? WHERE id = ?",
        (now, task["id"]),
    )
    db.commit()
    return json.dumps({"name": task_name, "status": "cancelled"}, ensure_ascii=False)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        init_options = server.create_initialization_options()
        await server.run(read_stream, write_stream, init_options)


if __name__ == "__main__":
    asyncio.run(main())
