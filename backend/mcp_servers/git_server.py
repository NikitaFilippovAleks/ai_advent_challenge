"""Git MCP-сервер — предоставляет инструменты для работы с Git-репозиториями.

Запускается как subprocess через stdio-транспорт.
Инструменты: git_status, git_log, git_diff, git_branches.
"""

import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

server = Server("git-server")


async def _run_git(repo_path: str, *args: str) -> str:
    """Выполняет git-команду и возвращает результат."""
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", repo_path, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        error = stderr.decode().strip()
        return f"Ошибка git: {error}" if error else f"git завершился с кодом {proc.returncode}"

    return stdout.decode().strip() or "(пусто)"


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Возвращает список доступных инструментов."""
    return [
        Tool(
            name="git_status",
            description="Показывает статус git-репозитория (изменённые, добавленные, неотслеживаемые файлы)",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Путь к git-репозиторию",
                    },
                },
                "required": ["repo_path"],
            },
        ),
        Tool(
            name="git_log",
            description="Показывает историю коммитов (хеш + сообщение)",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Путь к git-репозиторию",
                    },
                    "max_count": {
                        "type": "integer",
                        "description": "Максимальное количество коммитов (по умолчанию 10)",
                        "default": 10,
                    },
                    "branch": {
                        "type": "string",
                        "description": "Ветка (по умолчанию текущая)",
                    },
                },
                "required": ["repo_path"],
            },
        ),
        Tool(
            name="git_diff",
            description="Показывает изменения в файлах (diff)",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Путь к git-репозиторию",
                    },
                    "cached": {
                        "type": "boolean",
                        "description": "Показать только staged-изменения (по умолчанию false)",
                        "default": False,
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Путь к конкретному файлу (по умолчанию все файлы)",
                    },
                },
                "required": ["repo_path"],
            },
        ),
        Tool(
            name="git_branches",
            description="Показывает список всех веток (локальных и удалённых)",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Путь к git-репозиторию",
                    },
                },
                "required": ["repo_path"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Выполняет вызов инструмента."""
    repo_path = arguments.get("repo_path", ".")

    if name == "git_status":
        result = await _run_git(repo_path, "status", "--porcelain")

    elif name == "git_log":
        max_count = str(arguments.get("max_count", 10))
        args = ["log", "--oneline", "-n", max_count]
        branch = arguments.get("branch")
        if branch:
            args.append(branch)
        result = await _run_git(repo_path, *args)

    elif name == "git_diff":
        args = ["diff"]
        if arguments.get("cached"):
            args.append("--cached")
        file_path = arguments.get("file_path")
        if file_path:
            args.extend(["--", file_path])
        result = await _run_git(repo_path, *args)

    elif name == "git_branches":
        result = await _run_git(repo_path, "branch", "-a")

    else:
        result = f"Неизвестный инструмент: {name}"

    return [TextContent(type="text", text=result)]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        init_options = server.create_initialization_options()
        await server.run(read_stream, write_stream, init_options)


if __name__ == "__main__":
    asyncio.run(main())
