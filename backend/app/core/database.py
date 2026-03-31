"""Инфраструктура базы данных: движок, фабрика сессий, инициализация.

Использует SQLAlchemy 2.0 async с aiosqlite в качестве драйвера.
Этот модуль НЕ содержит бизнес-запросов — только инфраструктуру.
"""

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text as sqlalchemy_text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base

# Путь к файлу БД: backend/data/chat.db
DB_PATH = Path(__file__).parent.parent.parent / "data" / "chat.db"

# Async-движок и фабрика сессий
engine = create_async_engine(
    f"sqlite+aiosqlite:///{DB_PATH}",
    echo=False,
)
async_session = async_sessionmaker(engine, expire_on_commit=False)


def _now_iso() -> str:
    """Возвращает текущее время в формате ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    """Инициализирует БД: создаёт директорию, таблицы и добавляет недостающие колонки."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Миграция: добавляем новые колонки в существующие таблицы (если их нет)
        await _migrate_add_columns(conn)


async def _migrate_add_columns(conn) -> None:
    """Добавляет новые колонки в существующие таблицы (ALTER TABLE IF NOT EXISTS)."""
    migrations = [
        ("conversations", "context_strategy", "TEXT DEFAULT 'summary'"),
        ("conversations", "active_branch_id", "INTEGER"),
        ("messages", "branch_id", "INTEGER"),
        ("conversation_facts", "category", "TEXT DEFAULT 'fact'"),
        ("conversations", "profile_id", "TEXT"),
    ]
    for table, column, col_type in migrations:
        try:
            await conn.execute(
                sqlalchemy_text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            )
        except Exception:
            # Колонка уже существует — пропускаем
            pass
