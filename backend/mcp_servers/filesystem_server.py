"""Filesystem MCP-сервер — активная работа с файлами проекта.

Запускается как subprocess через stdio-транспорт и предоставляет ассистенту
инструменты для:
  - листинга и чтения файлов проекта (read-only по всему репозиторию /repo)
  - поиска использований символа (find_usages) сразу в нескольких файлах
  - статического анализа Python/TS/JS файлов (LOC, функции, классы, импорты)
  - проверки соответствия файлов набору regex-правил (инварианты)
  - подготовки unified diff между текущим содержимым файла и предлагаемой версией
  - записи документации в /repo/docs/ (ADR, changelog, отчёты)

Безопасность:
  * Чтение: только внутри корня проекта (/repo). Бинарные и слишком большие
    файлы пропускаются. Системные директории (.git, node_modules, …) исключены.
  * Запись: разрешена строго внутри /repo/docs/ — ассистент не может править
    исходный код, только документацию и сгенерированные отчёты.
"""

import asyncio
import ast
import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

server = Server("filesystem-server")

# Корень проекта внутри контейнера (см. docker-compose.yml: ".:/repo")
PROJECT_ROOT = Path("/repo").resolve()

# Запись разрешена только сюда (поддиректории создаются автоматически)
ALLOWED_WRITE_DIR = (PROJECT_ROOT / "docs").resolve()

# Системные директории, в которые не лезем при поиске/листинге
SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
}

# Лимиты, чтобы не перегрузить контекст LLM
MAX_FILE_SIZE_BYTES = 512 * 1024  # 512 KB
MAX_MATCHES = 100
MAX_LIST_ENTRIES = 500
MAX_READ_LINES_DEFAULT = 400


@dataclass
class SafePath:
    """Результат проверки пути на принадлежность к разрешённой зоне."""

    ok: bool
    resolved: Path | None = None
    error: str | None = None


def _resolve_in_project(rel_or_abs: str) -> SafePath:
    """Преобразует пользовательский путь в абсолютный внутри PROJECT_ROOT.

    Защищает от path traversal: даже если передали `../etc/passwd`,
    результат должен оставаться внутри /repo.
    """
    raw = Path(rel_or_abs)
    candidate = raw if raw.is_absolute() else (PROJECT_ROOT / raw)
    try:
        resolved = candidate.resolve()
    except OSError as e:
        return SafePath(ok=False, error=f"Не удалось разрешить путь: {e}")

    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError:
        return SafePath(
            ok=False,
            error=f"Путь вне корня проекта: {resolved} (корень — {PROJECT_ROOT})",
        )
    return SafePath(ok=True, resolved=resolved)


def _is_binary(path: Path) -> bool:
    """Грубая эвристика «бинарный ли файл» — по NUL-байту в первых 8KB."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
        return b"\x00" in chunk
    except OSError:
        return True


def _iter_project_files(root: Path, file_glob: str = "*"):
    """Итератор по всем файлам, минуя SKIP_DIRS и слишком большие/бинарные."""
    for path in sorted(root.rglob(file_glob)):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        try:
            if path.stat().st_size > MAX_FILE_SIZE_BYTES:
                continue
        except OSError:
            continue
        if _is_binary(path):
            continue
        yield path


# ---------- Инструменты ----------


def _list_files(directory: str, file_glob: str = "*") -> dict:
    """Возвращает список файлов в директории (рекурсивно)."""
    safe = _resolve_in_project(directory)
    if not safe.ok:
        return {"error": safe.error, "entries": []}
    if not safe.resolved.is_dir():
        return {"error": f"Не директория: {directory}", "entries": []}

    entries = []
    truncated = False
    for path in _iter_project_files(safe.resolved, file_glob):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        entries.append({
            "path": str(path.relative_to(PROJECT_ROOT)),
            "size_bytes": size,
        })
        if len(entries) >= MAX_LIST_ENTRIES:
            truncated = True
            break

    return {"count": len(entries), "truncated": truncated, "entries": entries}


def _read_file(path: str, max_lines: int = MAX_READ_LINES_DEFAULT,
               start_line: int = 1) -> dict:
    """Читает файл, возвращает срез строк с номерами."""
    safe = _resolve_in_project(path)
    if not safe.ok:
        return {"error": safe.error}
    if not safe.resolved.is_file():
        return {"error": f"Файл не найден: {path}"}
    if _is_binary(safe.resolved):
        return {"error": "Файл бинарный"}
    try:
        text = safe.resolved.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return {"error": f"Ошибка чтения: {e}"}

    lines = text.splitlines()
    total = len(lines)
    start = max(1, start_line)
    end = min(total, start - 1 + max_lines)
    chunk = lines[start - 1:end]

    return {
        "path": str(safe.resolved.relative_to(PROJECT_ROOT)),
        "total_lines": total,
        "start_line": start,
        "end_line": end,
        "truncated": end < total,
        "content": "\n".join(f"{i:>5}: {line}" for i, line in enumerate(chunk, start=start)),
    }


def _find_usages(symbol: str, root: str = ".", file_glob: str = "*") -> dict:
    """Находит все строки в проекте, где встречается символ.

    Используется именно literal-search (escape regex), чтобы пользователь
    мог искать `GigaChatProvider`, не задумываясь про спецсимволы.
    """
    safe = _resolve_in_project(root)
    if not safe.ok:
        return {"error": safe.error, "matches": []}
    if not safe.resolved.is_dir():
        return {"error": f"Не директория: {root}", "matches": []}

    pattern = re.compile(rf"\b{re.escape(symbol)}\b")
    matches = []
    truncated = False
    files_scanned = 0

    for path in _iter_project_files(safe.resolved, file_glob):
        files_scanned += 1
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line_num, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                matches.append({
                    "file": str(path.relative_to(PROJECT_ROOT)),
                    "line": line_num,
                    "text": line.strip()[:200],
                })
                if len(matches) >= MAX_MATCHES:
                    truncated = True
                    break
        if truncated:
            break

    # Группировка по файлам — удобно для отчётов
    files_index: dict[str, int] = {}
    for m in matches:
        files_index[m["file"]] = files_index.get(m["file"], 0) + 1

    return {
        "symbol": symbol,
        "files_scanned": files_scanned,
        "total_matches": len(matches),
        "files": [
            {"file": f, "occurrences": c}
            for f, c in sorted(files_index.items(), key=lambda x: -x[1])
        ],
        "matches": matches,
        "truncated": truncated,
    }


def _analyze_python(path: Path, text: str) -> dict:
    """AST-анализ Python: функции, классы, импорты."""
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as e:
        return {"language": "python", "parse_error": str(e)}

    functions: list[str] = []
    classes: list[str] = []
    imports: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)

    return {
        "language": "python",
        "functions": sorted(set(functions)),
        "classes": sorted(set(classes)),
        "imports": sorted(set(imports)),
    }


def _analyze_jsts(text: str) -> dict:
    """Грубый regex-анализ TS/JS — без полноценного парсера AST."""
    funcs = re.findall(r"\bfunction\s+(\w+)", text)
    funcs += re.findall(r"\bconst\s+(\w+)\s*=\s*\(", text)
    classes = re.findall(r"\bclass\s+(\w+)", text)
    interfaces = re.findall(r"\binterface\s+(\w+)", text)
    imports = re.findall(r"from\s+['\"]([^'\"]+)['\"]", text)
    return {
        "language": "typescript/javascript",
        "functions": sorted(set(funcs)),
        "classes": sorted(set(classes)),
        "interfaces": sorted(set(interfaces)),
        "imports": sorted(set(imports)),
    }


def _analyze_file(path: str) -> dict:
    """Возвращает статистику и структуру файла."""
    safe = _resolve_in_project(path)
    if not safe.ok:
        return {"error": safe.error}
    if not safe.resolved.is_file():
        return {"error": f"Файл не найден: {path}"}
    if _is_binary(safe.resolved):
        return {"error": "Файл бинарный"}

    try:
        text = safe.resolved.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return {"error": f"Ошибка чтения: {e}"}

    lines = text.splitlines()
    blank = sum(1 for line in lines if not line.strip())
    code = len(lines) - blank

    result: dict = {
        "path": str(safe.resolved.relative_to(PROJECT_ROOT)),
        "size_bytes": safe.resolved.stat().st_size,
        "total_lines": len(lines),
        "blank_lines": blank,
        "code_lines": code,
    }

    suffix = safe.resolved.suffix.lower()
    if suffix == ".py":
        result.update(_analyze_python(safe.resolved, text))
    elif suffix in {".ts", ".tsx", ".js", ".jsx"}:
        result.update(_analyze_jsts(text))
    else:
        result["language"] = "text"

    return result


def _check_rules(directory: str, rules: list[dict], file_glob: str = "*") -> dict:
    """Проверяет файлы на соответствие списку правил.

    Каждое правило: {
      "name": "...",
      "pattern": "...",       # регулярка
      "must_match": bool,     # true — паттерн ОБЯЗАН встретиться, false — ЗАПРЕЩЁН
      "file_glob": "*.py"     # опционально, переопределяет общий
    }
    Возвращает список нарушений: файл, правило, строка (если найдена).
    """
    safe = _resolve_in_project(directory)
    if not safe.ok:
        return {"error": safe.error, "violations": []}
    if not safe.resolved.is_dir():
        return {"error": f"Не директория: {directory}", "violations": []}

    if not isinstance(rules, list) or not rules:
        return {"error": "rules должен быть непустым списком", "violations": []}

    # Подготовка: компиляция regex
    compiled_rules = []
    for idx, rule in enumerate(rules):
        try:
            compiled = re.compile(rule["pattern"])
        except (KeyError, re.error) as e:
            return {"error": f"Правило #{idx} некорректно: {e}", "violations": []}
        compiled_rules.append({
            "name": rule.get("name", f"rule_{idx}"),
            "pattern": rule["pattern"],
            "must_match": bool(rule.get("must_match", False)),
            "file_glob": rule.get("file_glob") or file_glob,
            "regex": compiled,
        })

    violations = []
    files_checked = 0

    # Проходим по каждому правилу — у каждого может быть свой file_glob
    for rule in compiled_rules:
        for path in _iter_project_files(safe.resolved, rule["file_glob"]):
            files_checked += 1
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            found_line = None
            for line_num, line in enumerate(text.splitlines(), start=1):
                if rule["regex"].search(line):
                    found_line = (line_num, line.strip()[:200])
                    break

            if rule["must_match"] and found_line is None:
                violations.append({
                    "rule": rule["name"],
                    "file": str(path.relative_to(PROJECT_ROOT)),
                    "kind": "missing_required_pattern",
                    "pattern": rule["pattern"],
                })
            elif (not rule["must_match"]) and found_line is not None:
                violations.append({
                    "rule": rule["name"],
                    "file": str(path.relative_to(PROJECT_ROOT)),
                    "kind": "forbidden_pattern_found",
                    "line": found_line[0],
                    "text": found_line[1],
                    "pattern": rule["pattern"],
                })

    return {
        "rules_count": len(compiled_rules),
        "files_checked": files_checked,
        "violations_count": len(violations),
        "violations": violations,
    }


def _compute_diff(path: str, new_content: str, context_lines: int = 3) -> dict:
    """Готовит unified diff между текущим содержимым файла и предлагаемым.

    Если файла нет — diff покажет добавление нового файла.
    """
    safe = _resolve_in_project(path)
    if not safe.ok:
        return {"error": safe.error}

    rel = str(safe.resolved.relative_to(PROJECT_ROOT))
    if safe.resolved.exists():
        if not safe.resolved.is_file():
            return {"error": f"Не файл: {path}"}
        if _is_binary(safe.resolved):
            return {"error": "Файл бинарный"}
        try:
            old = safe.resolved.read_text(encoding="utf-8", errors="ignore")
        except OSError as e:
            return {"error": f"Ошибка чтения: {e}"}
        is_new = False
    else:
        old = ""
        is_new = True

    diff_lines = list(difflib.unified_diff(
        old.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"a/{rel}",
        tofile=f"b/{rel}",
        n=context_lines,
    ))
    added = sum(1 for line in diff_lines
                if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_lines
                  if line.startswith("-") and not line.startswith("---"))

    return {
        "path": rel,
        "is_new_file": is_new,
        "lines_added": added,
        "lines_removed": removed,
        "no_changes": not diff_lines,
        "diff": "".join(diff_lines),
    }


def _write_doc(path: str, content: str, overwrite: bool = False) -> dict:
    """Записывает текстовый файл, но строго внутри /repo/docs/."""
    safe = _resolve_in_project(path)
    if not safe.ok:
        return {"saved": False, "error": safe.error}

    try:
        safe.resolved.relative_to(ALLOWED_WRITE_DIR)
    except ValueError:
        return {
            "saved": False,
            "error": f"Запись разрешена только внутри {ALLOWED_WRITE_DIR}",
        }

    if safe.resolved.exists() and not overwrite:
        return {
            "saved": False,
            "error": f"Файл уже существует: {path}. Передайте overwrite=true для перезаписи.",
        }

    try:
        safe.resolved.parent.mkdir(parents=True, exist_ok=True)
        safe.resolved.write_text(content, encoding="utf-8")
        return {
            "saved": True,
            "path": str(safe.resolved.relative_to(PROJECT_ROOT)),
            "size_bytes": safe.resolved.stat().st_size,
            "overwritten": overwrite and safe.resolved.exists(),
        }
    except OSError as e:
        return {"saved": False, "error": str(e)}


# ---------- Декларация инструментов ----------


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_project_files",
            description=(
                "Список файлов проекта в директории (рекурсивно), с фильтром по glob. "
                "Полезно перед find_usages / analyze_file, чтобы понять, что есть в папке."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Путь относительно корня проекта (например 'backend/app/modules')",
                    },
                    "file_glob": {
                        "type": "string",
                        "description": "Glob-фильтр, например '*.py' или '**/*.tsx'",
                        "default": "*",
                    },
                },
                "required": ["directory"],
            },
        ),
        Tool(
            name="read_project_file",
            description=(
                "Читает файл проекта и возвращает строки с номерами. "
                "Используй после list_project_files или find_usages, чтобы посмотреть содержимое."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Путь к файлу"},
                    "start_line": {
                        "type": "integer",
                        "description": "С какой строки читать (по умолчанию 1)",
                        "default": 1,
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": "Сколько строк вернуть (по умолчанию 400)",
                        "default": 400,
                    },
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="find_usages",
            description=(
                "Ищет ВСЕ места, где встречается имя символа (компонент, функция, "
                "API endpoint, переменная). Возвращает файлы, строки и сгруппированную "
                "статистику по файлам. Это основной инструмент для запросов вида "
                "'найди все места, где используется X'. "
                "Если пользователь просит СОХРАНИТЬ результаты в файл (например, "
                "'сохрани в docs/...'), сразу после этого инструмента вызывай write_doc — "
                "не создавай scheduled-задачи, не отвечай шаблоном в чате."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Имя символа (без кавычек), например 'GigaChatProvider'",
                    },
                    "root": {
                        "type": "string",
                        "description": "Корень поиска (по умолчанию весь проект)",
                        "default": ".",
                    },
                    "file_glob": {
                        "type": "string",
                        "description": "Фильтр файлов, например '*.py'",
                        "default": "*",
                    },
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="analyze_file",
            description=(
                "Анализирует файл: размер, число строк, для Python — функции/классы/импорты "
                "через AST, для TS/JS — те же сущности через regex. "
                "Используй для оценки структуры файла."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Путь к файлу"},
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="check_rules",
            description=(
                "Проверяет файлы директории на соответствие списку правил-инвариантов. "
                "Каждое правило задаёт regex-паттерн, который должен встречаться (must_match=true) "
                "или быть запрещён (must_match=false). Возвращает список нарушений. "
                "Используй для аудита кода: 'проверь, что все роутеры тонкие', "
                "'убедись, что нет console.log в проде', и т.п."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Корень проверки"},
                    "rules": {
                        "type": "array",
                        "description": "Список правил",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "pattern": {"type": "string"},
                                "must_match": {"type": "boolean"},
                                "file_glob": {"type": "string"},
                            },
                            "required": ["pattern"],
                        },
                    },
                    "file_glob": {
                        "type": "string",
                        "description": "Общий фильтр файлов (если в правиле не задан свой)",
                        "default": "*",
                    },
                },
                "required": ["directory", "rules"],
            },
        ),
        Tool(
            name="compute_diff",
            description=(
                "Готовит unified diff между текущим содержимым файла и предлагаемой версией. "
                "Используй ПЕРЕД write_doc, чтобы пользователь мог увидеть изменения, "
                "или просто чтобы показать список планируемых правок."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Путь к файлу"},
                    "new_content": {
                        "type": "string",
                        "description": "Новое содержимое целиком",
                    },
                    "context_lines": {
                        "type": "integer",
                        "description": "Контекстных строк вокруг изменений (по умолчанию 3)",
                        "default": 3,
                    },
                },
                "required": ["path", "new_content"],
            },
        ),
        Tool(
            name="write_doc",
            description=(
                "ЕДИНСТВЕННЫЙ способ сохранить/создать/записать файл с документацией "
                "или отчётом в проекте. Вызывай его всегда, когда пользователь говорит "
                "'сохрани', 'создай файл', 'запиши отчёт', 'положи в docs/...', "
                "'сгенерируй README/ADR/changelog'. Записывает текстовый файл "
                "(Markdown, TXT и т.п.) СТРОГО ВНУТРИ /repo/docs/ — путь начинается с 'docs/'. "
                "Запись вне docs/ запрещена. "
                "НЕ используй scheduler/create_scheduled_task для разовой генерации отчёта — "
                "это однократная операция, выполни её прямо сейчас через write_doc."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Путь к файлу (например 'docs/adr/0001-x.md')",
                    },
                    "content": {"type": "string", "description": "Полное содержимое"},
                    "overwrite": {
                        "type": "boolean",
                        "description": "Разрешить перезапись существующего файла",
                        "default": False,
                    },
                },
                "required": ["path", "content"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "list_project_files":
        result = _list_files(arguments["directory"], arguments.get("file_glob", "*"))
    elif name == "read_project_file":
        result = _read_file(
            path=arguments["path"],
            start_line=arguments.get("start_line", 1),
            max_lines=arguments.get("max_lines", MAX_READ_LINES_DEFAULT),
        )
    elif name == "find_usages":
        result = _find_usages(
            symbol=arguments["symbol"],
            root=arguments.get("root", "."),
            file_glob=arguments.get("file_glob", "*"),
        )
    elif name == "analyze_file":
        result = _analyze_file(arguments["path"])
    elif name == "check_rules":
        result = _check_rules(
            directory=arguments["directory"],
            rules=arguments.get("rules", []),
            file_glob=arguments.get("file_glob", "*"),
        )
    elif name == "compute_diff":
        result = _compute_diff(
            path=arguments["path"],
            new_content=arguments["new_content"],
            context_lines=arguments.get("context_lines", 3),
        )
    elif name == "write_doc":
        result = _write_doc(
            path=arguments["path"],
            content=arguments["content"],
            overwrite=arguments.get("overwrite", False),
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
