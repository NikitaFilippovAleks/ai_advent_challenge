# Композиция MCP-инструментов — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Создать MCP-сервер `research_server.py` с тремя инструментами (search_files, summarize_text, save_to_file), образующими пайплайн поиск → обработка → сохранение.

**Architecture:** Один новый MCP-сервер по образцу `git_server.py`. Существующая инфраструктура (AgentRunner, MCPManager, ChatService, фронтенд) не меняется. Сервер регистрируется в `mcp_servers.json` с `enabled: true`.

**Tech Stack:** Python 3.12, mcp SDK (Server, stdio_server, TextContent, Tool), asyncio, pathlib, re, json.

---

## Файловая структура

| Действие | Файл | Ответственность |
|----------|------|-----------------|
| Создать | `backend/mcp_servers/research_server.py` | MCP-сервер с 3 инструментами |
| Изменить | `backend/data/mcp_servers.json` | Добавить запись "research" |
| Изменить | `.claude/CLAUDE.md` | Обновить описание MCP-серверов |

---

### Task 1: Инструмент search_files

**Files:**
- Create: `backend/mcp_servers/research_server.py`

- [ ] **Step 1: Создать скелет research_server.py с инструментом search_files**

```python
"""Research MCP-сервер — поиск по файлам, структурирование текста, сохранение в файл.

Запускается как subprocess через stdio-транспорт.
Инструменты: search_files, summarize_text, save_to_file.
"""

import asyncio
import json
import os
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
    else:
        result = {"error": f"Неизвестный инструмент: {name}"}

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        init_options = server.create_initialization_options()
        await server.run(read_stream, write_stream, init_options)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Проверить, что файл синтаксически корректен**

Выполнить в контейнере бэкенда:
```bash
docker compose exec backend python -c "import py_compile; py_compile.compile('mcp_servers/research_server.py', doraise=True)"
```
Ожидаемый результат: без ошибок.

---

### Task 2: Инструмент summarize_text

**Files:**
- Modify: `backend/mcp_servers/research_server.py`

- [ ] **Step 1: Добавить функцию _summarize_text перед list_tools**

Вставить после функции `_search_files`:

```python
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
```

- [ ] **Step 2: Добавить Tool-определение summarize_text в list_tools**

Добавить в массив return внутри `list_tools()`, после Tool для search_files:

```python
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
```

- [ ] **Step 3: Добавить обработку summarize_text в call_tool**

В функции `call_tool`, после блока `if name == "search_files":`, добавить:

```python
    elif name == "summarize_text":
        result = _summarize_text(
            text=arguments["text"],
            max_lines=arguments.get("max_lines", 50),
            fmt=arguments.get("format", "plain"),
        )
```

- [ ] **Step 4: Проверить синтаксис**

```bash
docker compose exec backend python -c "import py_compile; py_compile.compile('mcp_servers/research_server.py', doraise=True)"
```
Ожидаемый результат: без ошибок.

---

### Task 3: Инструмент save_to_file

**Files:**
- Modify: `backend/mcp_servers/research_server.py`

- [ ] **Step 1: Добавить функцию _save_to_file и константу ALLOWED_DIR перед list_tools**

Вставить после функции `_summarize_text`:

```python
# Безопасность: запись разрешена только в эту директорию
ALLOWED_DIR = Path("/app/data")


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
```

- [ ] **Step 2: Добавить Tool-определение save_to_file в list_tools**

Добавить в массив return внутри `list_tools()`, после Tool для summarize_text:

```python
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
```

- [ ] **Step 3: Добавить обработку save_to_file в call_tool**

В функции `call_tool`, после блока `elif name == "summarize_text":`, добавить:

```python
    elif name == "save_to_file":
        result = _save_to_file(
            path=arguments["path"],
            content=arguments["content"],
        )
```

- [ ] **Step 4: Проверить синтаксис**

```bash
docker compose exec backend python -c "import py_compile; py_compile.compile('mcp_servers/research_server.py', doraise=True)"
```
Ожидаемый результат: без ошибок.

---

### Task 4: Регистрация сервера в конфигурации

**Files:**
- Modify: `backend/data/mcp_servers.json`

- [ ] **Step 1: Добавить запись "research" в mcp_servers.json**

В объект `"servers"` добавить после записи `"scheduler"`:

```json
    "research": {
      "command": "python",
      "args": ["mcp_servers/research_server.py"],
      "enabled": true
    }
```

Итоговый файл:
```json
{
  "servers": {
    "git": {
      "command": "python",
      "args": ["mcp_servers/git_server.py"],
      "enabled": true
    },
    "scheduler": {
      "command": "python",
      "args": ["mcp_servers/scheduler_server.py"],
      "enabled": true
    },
    "research": {
      "command": "python",
      "args": ["mcp_servers/research_server.py"],
      "enabled": true
    }
  }
}
```

---

### Task 5: Проверка пайплайна — автоматическая цепочка

**Files:** (нет изменений — только ручная проверка)

- [ ] **Step 1: Пересобрать и запустить контейнеры**

```bash
make build
```

Ожидаемый результат: контейнеры стартуют без ошибок, в логах бэкенда видно подключение research-server.

- [ ] **Step 2: Проверить подключение через API**

```bash
docker compose exec backend python -c "
import asyncio, json

async def check():
    import httpx
    async with httpx.AsyncClient(base_url='http://localhost:8000') as c:
        r = await c.get('/api/mcp/servers')
        servers = r.json()
        for s in servers:
            print(f\"{s['name']}: connected={s['connected']}, tools={s['tool_count']}\")
        r = await c.get('/api/mcp/tools')
        tools = r.json()
        for t in tools:
            if t['server'] == 'research':
                print(f\"  tool: {t['name']} — {t['description'][:60]}\")

asyncio.run(check())
"
```

Ожидаемый результат: research сервер connected=True, tool_count=3, и три инструмента в списке.

- [ ] **Step 3: Протестировать пайплайн через чат**

Открыть фронтенд (http://localhost:5173), написать в чат:

> Найди все TODO и FIXME в Python-файлах в директории /app и сохрани отчёт в /app/data/reports/todo-report.md в формате markdown

Ожидаемый результат:
1. В стриме видны события tool_call → tool_result для search_files
2. Затем tool_call → tool_result для summarize_text
3. Затем tool_call → tool_result для save_to_file
4. LLM отвечает текстом с описанием результата
5. Файл `/app/data/reports/todo-report.md` создан в контейнере

Проверить файл:
```bash
docker compose exec backend cat /app/data/reports/todo-report.md
```

---

### Task 6: Обновить CLAUDE.md

**Files:**
- Modify: `.claude/CLAUDE.md`

- [ ] **Step 1: Добавить описание research_server в секцию MCP-серверов**

В секции «Бэкенд (Python 3.12, FastAPI) — доменно-модульная архитектура:» после строки про `backend/mcp_servers/scheduler_server.py` добавить:

```
- `backend/mcp_servers/research_server.py` — MCP-сервер для исследования файлов (3 инструмента: search_files, summarize_text, save_to_file), демонстрирует композицию инструментов в пайплайн
```
