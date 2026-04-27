"""Автоиндексация документации проекта (README + docs/) в коллекцию project_docs.

Запускается при старте приложения из lifespan. Считает быстрый сигнатурный
хеш текущего набора файлов и сравнивает его с прошлым прогоном (lock-файл),
чтобы не дёргать индексер впустую при перезапусках.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from app.modules.indexing.service import IndexingService

logger = logging.getLogger(__name__)

# Имя коллекции для документации проекта.
PROJECT_DOCS_COLLECTION = "project_docs"

# Корень репозитория внутри backend-контейнера (см. docker-compose: -.:/repo).
# Локально для тестов скрипта пробуем родительскую директорию backend/.
_REPO_ROOT_CANDIDATES = [Path("/repo"), Path(__file__).resolve().parents[4]]

# Файл-метка состояния последней индексации (mtime+size signature).
_LOCK_DIR = Path(__file__).resolve().parents[3] / "data"
_LOCK_FILE = _LOCK_DIR / "project_docs.lock"


def _find_repo_root() -> Path | None:
    """Возвращает первый существующий каталог-кандидат корня репозитория."""
    for candidate in _REPO_ROOT_CANDIDATES:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _collect_doc_paths(repo_root: Path) -> list[Path]:
    """Собирает список md-файлов: README.md (корень) + все *.md из docs/."""
    paths: list[Path] = []
    readme = repo_root / "README.md"
    if readme.exists():
        paths.append(readme)
    docs_dir = repo_root / "docs"
    if docs_dir.exists() and docs_dir.is_dir():
        # Сортируем для детерминизма сигнатуры
        paths.extend(sorted(docs_dir.rglob("*.md")))
    return paths


def _compute_signature(paths: list[Path]) -> str:
    """Считает быстрый хеш по (путь, mtime, size) — без чтения содержимого.

    Этого достаточно: если хоть один файл изменился — хеш поменяется
    и переиндексация запустится. Само содержимое файлов проверяется
    уже в IndexingService по SHA-256, так что невидимая правка не
    приведёт к лишней работе на embedding-API.
    """
    h = hashlib.sha256()
    for p in paths:
        try:
            stat = p.stat()
        except OSError:
            continue
        h.update(str(p).encode("utf-8"))
        h.update(b"\0")
        h.update(str(stat.st_mtime_ns).encode("utf-8"))
        h.update(b"\0")
        h.update(str(stat.st_size).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def _read_lock() -> str | None:
    """Читает сохранённую сигнатуру предыдущего прогона."""
    try:
        return _LOCK_FILE.read_text(encoding="utf-8").strip() or None
    except FileNotFoundError:
        return None
    except OSError:
        return None


def _write_lock(signature: str) -> None:
    """Сохраняет текущую сигнатуру."""
    try:
        _LOCK_DIR.mkdir(parents=True, exist_ok=True)
        _LOCK_FILE.write_text(signature, encoding="utf-8")
    except OSError as e:
        logger.warning("Не удалось записать lock-файл индекса project_docs: %s", e)


async def index_project_docs(service: IndexingService) -> None:
    """Индексирует README + docs/**/*.md в коллекцию project_docs.

    Если сигнатура файлов не менялась с прошлого прогона — пропускает работу.
    При изменениях полностью переиндексирует коллекцию (replace_collection=True),
    чтобы удалённые/переименованные файлы исчезали из индекса.
    """
    repo_root = _find_repo_root()
    if repo_root is None:
        logger.warning(
            "Корень репозитория не найден (ожидался /repo или %s) — "
            "автоиндексация project_docs пропущена",
            _REPO_ROOT_CANDIDATES[1],
        )
        return

    paths = _collect_doc_paths(repo_root)
    if not paths:
        logger.warning(
            "В %s не найдены README.md/docs/*.md — индексация project_docs пропущена",
            repo_root,
        )
        return

    signature = _compute_signature(paths)
    previous = _read_lock()
    if signature == previous:
        logger.info(
            "project_docs не менялись (%d файлов) — переиндексация пропущена",
            len(paths),
        )
        return

    logger.info(
        "Индексирую project_docs: %d файлов из %s в коллекцию '%s'",
        len(paths),
        repo_root,
        PROJECT_DOCS_COLLECTION,
    )

    try:
        await service.index_documents(
            paths=[str(p) for p in paths],
            strategy_name="structural",
            collection=PROJECT_DOCS_COLLECTION,
            replace_collection=True,
        )
    except Exception as e:
        logger.error("Ошибка автоиндексации project_docs: %s", e, exc_info=True)
        return

    _write_lock(signature)
    logger.info("project_docs проиндексированы (signature=%s)", signature[:12])
