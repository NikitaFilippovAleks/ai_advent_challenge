"""Support MCP-сервер — данные о пользователях и тикетах поддержки.

Запускается как subprocess через stdio-транспорт.
Источник данных — JSON-файл /app/data/support_tickets.json.

Инструменты:
    - get_user(user_id)              — карточка пользователя (план, email).
    - list_user_tickets(user_id, status?) — все тикеты пользователя.
    - get_ticket(ticket_id)          — полные данные тикета (история, метаданные).
    - add_ticket_note(ticket_id, note) — внутренняя заметка от ассистента.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

server = Server("support-server")

# Путь к JSON-файлу с данными поддержки.
# Файл-источник примонтирован вместе с остальными data/*.json в контейнер.
DATA_FILE = Path("/app/data/support_tickets.json")


def _load_data() -> dict:
    """Загружает данные поддержки из JSON-файла."""
    if not DATA_FILE.exists():
        return {"users": {}, "tickets": {}}
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"users": {}, "tickets": {}}
    # Гарантируем наличие ключей даже в кривом файле
    data.setdefault("users", {})
    data.setdefault("tickets", {})
    return data


def _save_data(data: dict) -> None:
    """Сохраняет данные поддержки в JSON-файл."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _get_user(user_id: str) -> dict:
    """Возвращает карточку пользователя по ID."""
    data = _load_data()
    user = data["users"].get(user_id)
    if not user:
        return {"error": f"Пользователь не найден: {user_id}"}
    return user


def _list_user_tickets(user_id: str, status: str = "") -> dict:
    """Возвращает список тикетов пользователя, опционально фильтрует по статусу."""
    data = _load_data()
    items = [t for t in data["tickets"].values() if t.get("user_id") == user_id]
    if status:
        items = [t for t in items if t.get("status", "").lower() == status.lower()]
    # Новые тикеты — первыми
    items.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return {
        "user_id": user_id,
        "count": len(items),
        "tickets": [
            {
                "id": t["id"],
                "subject": t.get("subject", ""),
                "status": t.get("status", ""),
                "priority": t.get("priority", ""),
                "product": t.get("product", ""),
                "created_at": t.get("created_at", ""),
            }
            for t in items
        ],
    }


def _get_ticket(ticket_id: str) -> dict:
    """Возвращает полные данные тикета по ID."""
    data = _load_data()
    ticket = data["tickets"].get(ticket_id)
    if not ticket:
        return {"error": f"Тикет не найден: {ticket_id}"}
    # Дополняем карточкой пользователя — ассистенту удобнее ответить
    user = data["users"].get(ticket.get("user_id"))
    return {
        **ticket,
        "user": user,  # может быть None, если пользователь не найден
    }


def _add_ticket_note(ticket_id: str, note: str) -> dict:
    """Добавляет внутреннюю заметку (от ассистента) в историю тикета."""
    data = _load_data()
    ticket = data["tickets"].get(ticket_id)
    if not ticket:
        return {"error": f"Тикет не найден: {ticket_id}"}

    history = ticket.setdefault("history", [])
    entry = {
        "role": "assistant_note",
        "content": note,
        "timestamp": datetime.now().isoformat(),
    }
    history.append(entry)
    ticket["updated_at"] = entry["timestamp"]
    _save_data(data)
    return {"added": True, "ticket_id": ticket_id, "entry": entry}


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Возвращает список доступных инструментов."""
    return [
        Tool(
            name="get_user",
            description=(
                "Возвращает карточку пользователя по его ID: имя, email, план, "
                "дату регистрации. Используй, когда в запросе фигурирует user_id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "Идентификатор пользователя (например, user_001)",
                    },
                },
                "required": ["user_id"],
            },
        ),
        Tool(
            name="list_user_tickets",
            description=(
                "Возвращает список тикетов пользователя. Можно отфильтровать по "
                "статусу (open/resolved/in_progress)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "Идентификатор пользователя",
                    },
                    "status": {
                        "type": "string",
                        "description": "Фильтр по статусу (опционально)",
                        "default": "",
                    },
                },
                "required": ["user_id"],
            },
        ),
        Tool(
            name="get_ticket",
            description=(
                "Возвращает полную карточку тикета: тема, описание, статус, "
                "приоритет, продукт, историю сообщений и данные пользователя. "
                "Используй ВСЕГДА, если в запросе указан ID тикета."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "string",
                        "description": "Идентификатор тикета (например, T-1042)",
                    },
                },
                "required": ["ticket_id"],
            },
        ),
        Tool(
            name="add_ticket_note",
            description=(
                "Добавляет внутреннюю заметку ассистента к тикету (видна "
                "только сотрудникам поддержки). Используй, чтобы зафиксировать "
                "вывод диагностики или предпринятый шаг."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "string",
                        "description": "Идентификатор тикета",
                    },
                    "note": {
                        "type": "string",
                        "description": "Текст заметки",
                    },
                },
                "required": ["ticket_id", "note"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Выполняет вызов инструмента."""
    if name == "get_user":
        result = _get_user(arguments["user_id"])
    elif name == "list_user_tickets":
        result = _list_user_tickets(
            user_id=arguments["user_id"],
            status=arguments.get("status", ""),
        )
    elif name == "get_ticket":
        result = _get_ticket(arguments["ticket_id"])
    elif name == "add_ticket_note":
        result = _add_ticket_note(
            ticket_id=arguments["ticket_id"],
            note=arguments["note"],
        )
    else:
        result = {"error": f"Неизвестный инструмент: {name}"}

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        init_options = server.create_initialization_options()
        await server.run(read_stream, write_stream, init_options)


if __name__ == "__main__":
    asyncio.run(main())
