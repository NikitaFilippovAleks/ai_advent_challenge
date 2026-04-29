"""CLI-точка входа AI code review.

Запуск:
    python -m app.modules.code_review.cli \\
        --base origin/master --head HEAD --output /repo/.review-output.md

Используется как локально (через docker compose run --rm backend ...),
так и в GitHub Actions (workflow `.github/workflows/ai-code-review.yml`).
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from app.core.database import init_db
from app.modules.code_review.dependencies import get_code_review_service

# Корень репозитория, смонтированный в контейнере docker-compose.
# Соответствует volume `.:/repo` в docker-compose.yml.
DEFAULT_REPO_ROOT = "/repo"

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="code_review",
        description="AI code review для PR — генерирует Markdown-ревью по diff'у.",
    )
    parser.add_argument(
        "--base",
        default="origin/master",
        help="Базовая ревизия для diff (по умолчанию: origin/master).",
    )
    parser.add_argument(
        "--head",
        default="HEAD",
        help="Целевая ревизия для diff (по умолчанию: HEAD).",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Путь к файлу, в который записать Markdown-ревью.",
    )
    parser.add_argument(
        "--repo-root",
        default=DEFAULT_REPO_ROOT,
        help=(
            "Корень репозитория для git-команд "
            f"(по умолчанию: {DEFAULT_REPO_ROOT})."
        ),
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    # Инициализация БД нужна, потому что IndexingService хранит
    # документы и чанки в SQLite.
    await init_db()

    service = get_code_review_service()
    try:
        review_md = await service.review(
            base=args.base,
            head=args.head,
            repo_root=args.repo_root,
        )
    except Exception as exc:
        logger.exception("Сбой во время генерации ревью")
        error_md = (
            "## Ошибка\n\n"
            f"Не удалось получить AI-ревью: `{type(exc).__name__}: {exc}`\n\n"
            "Проверь логи job'а в GitHub Actions."
        )
        Path(args.output).write_text(error_md, encoding="utf-8")
        sys.stdout.write(error_md + "\n")
        return 1

    Path(args.output).write_text(review_md, encoding="utf-8")
    sys.stdout.write(review_md + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = _parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
