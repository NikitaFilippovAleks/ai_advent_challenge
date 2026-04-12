"""System MCP-сервер — системная информация и утилиты.

Запускается как subprocess через stdio-транспорт.
Инструменты: current_datetime, disk_usage, list_processes, env_info.
"""

import asyncio
import json
import os
import platform
import shutil
from datetime import datetime

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

server = Server("system-server")


def _current_datetime(timezone: str = "local") -> dict:
    """Возвращает текущую дату и время."""
    now = datetime.now()
    return {
        "datetime": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "timestamp": int(now.timestamp()),
    }


def _disk_usage(path: str = "/") -> dict:
    """Информация об использовании диска."""
    try:
        usage = shutil.disk_usage(path)
        return {
            "path": path,
            "total_gb": round(usage.total / (1024 ** 3), 2),
            "used_gb": round(usage.used / (1024 ** 3), 2),
            "free_gb": round(usage.free / (1024 ** 3), 2),
            "used_percent": round(usage.used / usage.total * 100, 1),
        }
    except OSError as e:
        return {"error": str(e)}


async def _list_processes(filter_name: str = "") -> dict:
    """Список запущенных процессов (через ps)."""
    proc = await asyncio.create_subprocess_exec(
        "ps", "aux", "--no-header" if platform.system() != "Darwin" else "",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    lines = stdout.decode(errors="ignore").strip().splitlines()

    # Заголовок ps aux — первая строка
    processes = []
    for line in lines[:200]:  # Ограничиваем количество
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        cmd = parts[10]
        if filter_name and filter_name.lower() not in cmd.lower():
            continue
        processes.append({
            "user": parts[0],
            "pid": parts[1],
            "cpu": parts[2],
            "mem": parts[3],
            "command": cmd[:200],
        })

    return {
        "count": len(processes),
        "processes": processes[:50],  # Макс 50 для контекста LLM
    }


def _env_info() -> dict:
    """Информация о системном окружении."""
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "hostname": platform.node(),
        "cpu_count": os.cpu_count(),
        "cwd": os.getcwd(),
        "user": os.environ.get("USER", os.environ.get("USERNAME", "unknown")),
    }


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Возвращает список доступных инструментов."""
    return [
        Tool(
            name="current_datetime",
            description="Возвращает текущую дату, время, день недели и unix-таймстемп",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="disk_usage",
            description="Показывает использование дискового пространства (всего, занято, свободно)",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Путь к разделу (по умолчанию '/')",
                        "default": "/",
                    },
                },
            },
        ),
        Tool(
            name="list_processes",
            description="Показывает список запущенных процессов с CPU/MEM. Можно фильтровать по имени",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter_name": {
                        "type": "string",
                        "description": "Фильтр по имени процесса (опционально)",
                        "default": "",
                    },
                },
            },
        ),
        Tool(
            name="env_info",
            description=(
                "Информация о системном окружении: ОС, версия, архитектура, "
                "Python, hostname, CPU, текущая директория"
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Выполняет вызов инструмента."""
    if name == "current_datetime":
        result = _current_datetime()
    elif name == "disk_usage":
        result = _disk_usage(arguments.get("path", "/"))
    elif name == "list_processes":
        result = await _list_processes(arguments.get("filter_name", ""))
    elif name == "env_info":
        result = _env_info()
    else:
        result = {"error": f"Неизвестный инструмент: {name}"}

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        init_options = server.create_initialization_options()
        await server.run(read_stream, write_stream, init_options)


if __name__ == "__main__":
    asyncio.run(main())
