"""Сбор diff и списка изменённых файлов через git CLI.

Чистая утилита без зависимостей от LLM/RAG — её можно тестировать изолированно.
"""

import logging
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Жёсткий лимит на размер diff'а, передаваемого в LLM.
# При превышении — обрезаем и помечаем truncated=True.
MAX_DIFF_CHARS = 40_000


@dataclass
class DiffPayload:
    """Результат сбора diff для PR."""

    files: list[str]
    diff_text: str
    truncated: bool


class GitDiffError(RuntimeError):
    """Ошибка сбора diff (не найден base/head, git не установлен и т.п.)."""


def _run_git(args: list[str], cwd: str) -> str:
    """Выполняет git-команду и возвращает stdout. При сбое — GitDiffError."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitDiffError("git CLI не найден в PATH") from exc

    if result.returncode != 0:
        # stderr пишет git — содержит понятное сообщение об ошибке
        raise GitDiffError(
            f"git {' '.join(args)} → exit {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout


def collect_diff(base: str, head: str, repo_root: str) -> DiffPayload:
    """Собирает diff между base и head для PR.

    Используется тройная точка `base...head` — diff показывает изменения,
    внесённые в head относительно общего предка с base. Это стандартный
    «PR-diff» (как `gh pr diff`).
    """
    # Список изменённых файлов
    files_raw = _run_git(["diff", "--name-only", f"{base}...{head}"], repo_root)
    files = [line.strip() for line in files_raw.splitlines() if line.strip()]

    # Сам diff
    diff_text = _run_git(["diff", f"{base}...{head}"], repo_root)

    truncated = False
    if len(diff_text) > MAX_DIFF_CHARS:
        truncated = True
        diff_text = diff_text[:MAX_DIFF_CHARS]
        logger.warning(
            "Diff обрезан до %d символов (исходный размер больше)", MAX_DIFF_CHARS
        )

    return DiffPayload(files=files, diff_text=diff_text, truncated=truncated)
