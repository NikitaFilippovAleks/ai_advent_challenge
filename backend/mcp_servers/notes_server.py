"""Notes MCP-сервер — управление заметками (CRUD).

Запускается как subprocess через stdio-транспорт.
Инструменты: create_note, get_note, list_notes, search_notes, delete_note.
Данные хранятся в JSON-файле /app/data/notes.json.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

server = Server("notes-server")

# Файл хранения заметок
NOTES_FILE = Path("/app/data/notes.json")


def _load_notes() -> dict:
    """Загружает заметки из файла."""
    if not NOTES_FILE.exists():
        return {}
    try:
        return json.loads(NOTES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_notes(notes: dict) -> None:
    """Сохраняет заметки в файл."""
    NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    NOTES_FILE.write_text(
        json.dumps(notes, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _create_note(title: str, content: str, tags: list[str] | None = None) -> dict:
    """Создаёт новую заметку."""
    notes = _load_notes()
    note_id = uuid4().hex[:8]
    now = datetime.now().isoformat()
    note = {
        "id": note_id,
        "title": title,
        "content": content,
        "tags": tags or [],
        "created_at": now,
        "updated_at": now,
    }
    notes[note_id] = note
    _save_notes(notes)
    return {"created": True, "note": note}


def _get_note(note_id: str) -> dict:
    """Возвращает заметку по ID."""
    notes = _load_notes()
    note = notes.get(note_id)
    if not note:
        return {"error": f"Заметка не найдена: {note_id}"}
    return note


def _list_notes(tag: str = "") -> dict:
    """Возвращает список заметок, опционально фильтрует по тегу."""
    notes = _load_notes()
    items = list(notes.values())
    if tag:
        items = [n for n in items if tag.lower() in [t.lower() for t in n.get("tags", [])]]
    # Сортируем по дате обновления (новые первые)
    items.sort(key=lambda n: n.get("updated_at", ""), reverse=True)
    return {
        "count": len(items),
        "notes": [
            {
                "id": n["id"],
                "title": n["title"],
                "tags": n.get("tags", []),
                "created_at": n["created_at"],
                "preview": n["content"][:100] + ("…" if len(n["content"]) > 100 else ""),
            }
            for n in items
        ],
    }


def _search_notes(query: str) -> dict:
    """Ищет заметки по тексту в title и content."""
    notes = _load_notes()
    query_lower = query.lower()
    matches = []
    for note in notes.values():
        if (
            query_lower in note["title"].lower()
            or query_lower in note["content"].lower()
        ):
            matches.append({
                "id": note["id"],
                "title": note["title"],
                "tags": note.get("tags", []),
                "preview": note["content"][:100],
            })
    return {"count": len(matches), "matches": matches}


def _delete_note(note_id: str) -> dict:
    """Удаляет заметку по ID."""
    notes = _load_notes()
    if note_id not in notes:
        return {"error": f"Заметка не найдена: {note_id}"}
    title = notes[note_id]["title"]
    del notes[note_id]
    _save_notes(notes)
    return {"deleted": True, "id": note_id, "title": title}


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Возвращает список доступных инструментов."""
    return [
        Tool(
            name="create_note",
            description="Создаёт новую заметку с заголовком, содержимым и тегами",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Заголовок заметки",
                    },
                    "content": {
                        "type": "string",
                        "description": "Текст заметки",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Теги для категоризации (опционально)",
                    },
                },
                "required": ["title", "content"],
            },
        ),
        Tool(
            name="get_note",
            description="Возвращает полный текст заметки по её ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "note_id": {
                        "type": "string",
                        "description": "ID заметки",
                    },
                },
                "required": ["note_id"],
            },
        ),
        Tool(
            name="list_notes",
            description="Показывает список всех заметок. Можно фильтровать по тегу",
            inputSchema={
                "type": "object",
                "properties": {
                    "tag": {
                        "type": "string",
                        "description": "Фильтр по тегу (опционально)",
                        "default": "",
                    },
                },
            },
        ),
        Tool(
            name="search_notes",
            description="Ищет заметки по текстовому запросу в заголовке и содержимом",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Текст для поиска",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="delete_note",
            description="Удаляет заметку по ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "note_id": {
                        "type": "string",
                        "description": "ID заметки для удаления",
                    },
                },
                "required": ["note_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Выполняет вызов инструмента."""
    if name == "create_note":
        result = _create_note(
            title=arguments["title"],
            content=arguments["content"],
            tags=arguments.get("tags"),
        )
    elif name == "get_note":
        result = _get_note(arguments["note_id"])
    elif name == "list_notes":
        result = _list_notes(arguments.get("tag", ""))
    elif name == "search_notes":
        result = _search_notes(arguments["query"])
    elif name == "delete_note":
        result = _delete_note(arguments["note_id"])
    else:
        result = {"error": f"Неизвестный инструмент: {name}"}

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        init_options = server.create_initialization_options()
        await server.run(read_stream, write_stream, init_options)


if __name__ == "__main__":
    asyncio.run(main())
