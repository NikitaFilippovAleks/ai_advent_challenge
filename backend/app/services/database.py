"""Сервис базы данных SQLite для хранения истории диалогов.

Управляет таблицами conversations и messages через aiosqlite.
"""

import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

# Путь к файлу БД: backend/data/chat.db
DB_PATH = Path(__file__).parent.parent.parent / "data" / "chat.db"


async def init_db() -> None:
    """Инициализирует БД: создаёт директорию, таблицы и включает нужные прагмы."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA journal_mode = WAL")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT 'Новый диалог',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL
                    REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                usage_json TEXT,
                created_at TEXT NOT NULL
            )
        """)
        await db.commit()


@asynccontextmanager
async def get_db():
    """Async context manager для получения соединения с БД."""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
    finally:
        await db.close()


def _now_iso() -> str:
    """Возвращает текущее время в формате ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


async def create_conversation(title: str = "Новый диалог") -> dict:
    """Создаёт новый диалог и возвращает его данные."""
    conv_id = str(uuid.uuid4())
    now = _now_iso()
    async with get_db() as db:
        await db.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conv_id, title, now, now),
        )
        await db.commit()
    return {"id": conv_id, "title": title, "created_at": now, "updated_at": now}


async def list_conversations() -> list[dict]:
    """Возвращает список диалогов, отсортированных по дате обновления."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, title, updated_at FROM conversations ORDER BY updated_at DESC"
        )
        rows = await cursor.fetchall()
    return [{"id": r["id"], "title": r["title"], "updated_at": r["updated_at"]} for r in rows]


async def get_conversation(conversation_id: str) -> dict | None:
    """Возвращает диалог по ID или None если не найден."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?",
            (conversation_id,),
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "title": row["title"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def delete_conversation(conversation_id: str) -> bool:
    """Удаляет диалог и все его сообщения (CASCADE). Возвращает True если удалён."""
    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM conversations WHERE id = ?", (conversation_id,)
        )
        await db.commit()
    return cursor.rowcount > 0


async def update_conversation_title(conversation_id: str, title: str) -> None:
    """Обновляет название диалога."""
    async with get_db() as db:
        await db.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, _now_iso(), conversation_id),
        )
        await db.commit()


async def add_message(
    conversation_id: str,
    role: str,
    content: str,
    usage_json: str | None = None,
) -> int:
    """Добавляет сообщение в диалог и обновляет updated_at диалога."""
    now = _now_iso()
    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO messages (conversation_id, role, content, usage_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (conversation_id, role, content, usage_json, now),
        )
        await db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
        await db.commit()
    return cursor.lastrowid


async def get_messages(conversation_id: str) -> list[dict]:
    """Возвращает все сообщения диалога в хронологическом порядке."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT role, content, usage_json, created_at FROM messages "
            "WHERE conversation_id = ? ORDER BY id ASC",
            (conversation_id,),
        )
        rows = await cursor.fetchall()
    result = []
    for r in rows:
        msg = {
            "role": r["role"],
            "content": r["content"],
            "created_at": r["created_at"],
        }
        if r["usage_json"]:
            msg["usage"] = json.loads(r["usage_json"])
        result.append(msg)
    return result
