"""Seed-скрипт: индексирует FAQ-документы поддержки в коллекцию `support_faq`.

Запуск (внутри backend-контейнера):
    docker compose exec backend python /app/scripts/seed_support_faq.py

Делает init_db() и вызывает IndexingService.index_documents с
collection="support_faq" и replace_collection=True, чтобы коллекция
всегда соответствовала текущему набору файлов.
"""

import asyncio
import logging
from pathlib import Path

from app.core.database import init_db
from app.modules.indexing.service import IndexingService

# Каталог с Markdown-файлами FAQ (примонтирован в контейнер из backend/data/support_faq).
FAQ_DIR = Path("/app/data/support_faq")
COLLECTION = "support_faq"

logger = logging.getLogger(__name__)


async def _run() -> int:
    """Индексирует все .md из FAQ_DIR в коллекцию COLLECTION."""
    await init_db()

    if not FAQ_DIR.exists():
        logger.error("Каталог FAQ не найден: %s", FAQ_DIR)
        return 1

    paths = sorted(str(p) for p in FAQ_DIR.glob("*.md"))
    if not paths:
        logger.error("Не найдено ни одного .md файла в %s", FAQ_DIR)
        return 1

    logger.info("Индексирую %d файлов в коллекцию '%s'", len(paths), COLLECTION)
    service = IndexingService()
    results = await service.index_documents(
        paths=paths,
        # structural — учитывает заголовки Markdown, лучше для FAQ.
        strategy_name="structural",
        collection=COLLECTION,
        replace_collection=True,
    )
    for r in results:
        logger.info(
            "  ✓ %s — %d чанков (стратегия: %s)",
            r.filename,
            r.chunk_count,
            r.strategy,
        )
    logger.info("Готово. Файлов проиндексировано: %d", len(results))
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
