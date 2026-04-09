"""Research MCP-сервер — поиск по файлам, структурирование текста, сохранение в файл.

Запускается как subprocess через stdio-транспорт.
Инструменты: search_files, summarize_text, save_to_file.
"""

import asyncio
import json
import re
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

server = Server("research-server")

# Директории и файлы, которые пропускаем при поиске
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".mypy_cache"}

# Максимум совпадений чтобы не перегрузить контекст LLM
MAX_MATCHES = 50

# Безопасность: запись разрешена только в эту директорию
ALLOWED_DIR = Path("/app/data")


def _is_binary(file_path: Path) -> bool:
    """Проверяет, является ли файл бинарным (по первым 8KB)."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(8192)
        return b"\x00" in chunk
    except OSError:
        return True


def _search_files(directory: str, pattern: str, file_glob: str = "*") -> dict:
    """Рекурсивный поиск по содержимому файлов."""
    root = Path(directory)
    if not root.is_dir():
        return {"error": f"Директория не найдена: {directory}", "matches": [], "total": 0}

    regex = re.compile(pattern, re.IGNORECASE)
    matches = []
    truncated = False

    for path in sorted(root.rglob(file_glob)):
        # Пропускаем директории из SKIP_DIRS
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        if _is_binary(path):
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for line_num, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                matches.append({
                    "file": str(path.relative_to(root)),
                    "line": line_num,
                    "text": line.strip()[:200],
                })
                if len(matches) >= MAX_MATCHES:
                    truncated = True
                    break

        if truncated:
            break

    return {
        "matches": matches,
        "total": len(matches),
        "truncated": truncated,
    }


def _summarize_text(text: str, max_lines: int = 50, fmt: str = "plain") -> dict:
    """Структурирует и обрезает текст."""
    lines = text.splitlines()
    original_lines = len(lines)
    original_chars = len(text)
    truncated = len(lines) > max_lines

    result_lines = lines[:max_lines]

    if fmt == "markdown":
        header = f"# Результат ({original_lines} строк"
        if truncated:
            header += f", показано {max_lines}"
        header += ")\n"
        body = header + "\n```\n" + "\n".join(result_lines) + "\n```\n"
        body += f"\n**Статистика:** {original_lines} строк, {original_chars} символов"
        if truncated:
            body += f" (обрезано до {max_lines})"
    else:
        body = "\n".join(result_lines)

    return {
        "summary": body,
        "stats": {
            "original_lines": original_lines,
            "result_lines": len(result_lines),
            "chars": original_chars,
            "truncated": truncated,
        },
    }


def _save_to_file(path: str, content: str) -> dict:
    """Сохраняет текст в файл (только внутри ALLOWED_DIR)."""
    target = Path(path).resolve()
    allowed = ALLOWED_DIR.resolve()

    if not str(target).startswith(str(allowed)):
        return {"saved": False, "error": f"Запись разрешена только в {ALLOWED_DIR}"}

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {
            "saved": True,
            "path": str(target),
            "size_bytes": target.stat().st_size,
        }
    except OSError as e:
        return {"saved": False, "error": str(e)}


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Возвращает список доступных инструментов."""
    return [
        Tool(
            name="search_files",
            description=(
                "Рекурсивный поиск по содержимому файлов в директории. "
                "Возвращает совпадения с номерами строк."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Путь к директории для поиска",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Regex-паттерн для поиска в содержимом файлов",
                    },
                    "file_glob": {
                        "type": "string",
                        "description": "Glob-фильтр файлов, например '*.py' (по умолчанию '*')",
                        "default": "*",
                    },
                },
                "required": ["directory", "pattern"],
            },
        ),
        Tool(
            name="summarize_text",
            description=(
                "Структурирует и обрезает текст. Подсчитывает статистику "
                "(строки, символы). Может форматировать как plain или markdown."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Входной текст для обработки",
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": "Максимум строк в результате (по умолчанию 50)",
                        "default": 50,
                    },
                    "format": {
                        "type": "string",
                        "description": "Формат вывода: 'plain' или 'markdown' (по умолчанию 'plain')",
                        "enum": ["plain", "markdown"],
                        "default": "plain",
                    },
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="save_to_file",
            description=(
                "Сохраняет текст в файл. Создаёт директории если нужно. "
                "Запись ограничена директорией /app/data/."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Путь к файлу для записи (внутри /app/data/)",
                    },
                    "content": {
                        "type": "string",
                        "description": "Содержимое для записи в файл",
                    },
                },
                "required": ["path", "content"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Выполняет вызов инструмента."""
    if name == "search_files":
        result = _search_files(
            directory=arguments["directory"],
            pattern=arguments["pattern"],
            file_glob=arguments.get("file_glob", "*"),
        )
    elif name == "summarize_text":
        result = _summarize_text(
            text=arguments["text"],
            max_lines=arguments.get("max_lines", 50),
            fmt=arguments.get("format", "plain"),
        )
    elif name == "save_to_file":
        result = _save_to_file(
            path=arguments["path"],
            content=arguments["content"],
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
