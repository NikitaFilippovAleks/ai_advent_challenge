"""Репозиторий для работы с индексом документов и чанков.

Все операции с таблицами indexed_documents и document_chunks.
"""

import json
import uuid

from sqlalchemy import delete, select

from app.core.database import _now_iso, async_session
from app.models import DocumentChunk, IndexedDocument


# --- Документы ---


async def save_document(
    filename: str,
    title: str,
    content_hash: str,
    strategy: str,
    chunk_count: int,
) -> dict:
    """Создаёт запись проиндексированного документа."""
    now = _now_iso()
    doc = IndexedDocument(
        id=str(uuid.uuid4()),
        filename=filename,
        title=title,
        content_hash=content_hash,
        chunking_strategy=strategy,
        chunk_count=chunk_count,
        created_at=now,
    )
    async with async_session() as session:
        session.add(doc)
        await session.commit()
    return {
        "id": doc.id,
        "filename": doc.filename,
        "title": doc.title,
        "content_hash": doc.content_hash,
        "chunking_strategy": doc.chunking_strategy,
        "chunk_count": doc.chunk_count,
        "created_at": doc.created_at,
    }


async def save_chunks(document_id: str, chunks: list[dict]) -> None:
    """Сохраняет список чанков для документа."""
    now = _now_iso()
    async with async_session() as session:
        for c in chunks:
            chunk = DocumentChunk(
                document_id=document_id,
                chunk_index=c["chunk_index"],
                content=c["content"],
                embedding_json=json.dumps(c["embedding"]),
                source=c["source"],
                section=c.get("section"),
                char_start=c["char_start"],
                char_end=c["char_end"],
                created_at=now,
            )
            session.add(chunk)
        await session.commit()


async def get_all_documents() -> list[dict]:
    """Возвращает все проиндексированные документы."""
    async with async_session() as session:
        result = await session.execute(
            select(IndexedDocument).order_by(IndexedDocument.created_at.desc())
        )
        rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "filename": r.filename,
            "title": r.title,
            "chunking_strategy": r.chunking_strategy,
            "chunk_count": r.chunk_count,
            "created_at": r.created_at,
        }
        for r in rows
    ]


async def get_document(doc_id: str) -> dict | None:
    """Возвращает документ по ID или None."""
    async with async_session() as session:
        doc = await session.get(IndexedDocument, doc_id)
    if doc is None:
        return None
    return {
        "id": doc.id,
        "filename": doc.filename,
        "title": doc.title,
        "content_hash": doc.content_hash,
        "chunking_strategy": doc.chunking_strategy,
        "chunk_count": doc.chunk_count,
        "created_at": doc.created_at,
    }


async def delete_document(doc_id: str) -> bool:
    """Удаляет документ и все его чанки (каскадно)."""
    async with async_session() as session:
        doc = await session.get(IndexedDocument, doc_id)
        if doc is None:
            return False
        await session.delete(doc)
        await session.commit()
    return True


async def find_document_by_hash(content_hash: str, strategy: str) -> dict | None:
    """Ищет документ по хешу содержимого и стратегии (для пропуска переиндексации)."""
    async with async_session() as session:
        result = await session.execute(
            select(IndexedDocument).where(
                IndexedDocument.content_hash == content_hash,
                IndexedDocument.chunking_strategy == strategy,
            )
        )
        doc = result.scalar_one_or_none()
    if doc is None:
        return None
    return {
        "id": doc.id,
        "filename": doc.filename,
        "chunk_count": doc.chunk_count,
        "chunking_strategy": doc.chunking_strategy,
    }


async def get_all_chunks(document_ids: list[str] | None = None) -> list[dict]:
    """Загружает чанки с эмбеддингами. Опционально фильтрует по document_ids."""
    async with async_session() as session:
        query = select(DocumentChunk)
        if document_ids:
            query = query.where(DocumentChunk.document_id.in_(document_ids))
        result = await session.execute(query)
        rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "document_id": r.document_id,
            "chunk_index": r.chunk_index,
            "content": r.content,
            "embedding": json.loads(r.embedding_json),
            "source": r.source,
            "section": r.section,
            "char_start": r.char_start,
            "char_end": r.char_end,
        }
        for r in rows
    ]


async def get_document_ids_by_strategy(strategy: str) -> list[str]:
    """Возвращает ID документов, проиндексированных указанной стратегией."""
    async with async_session() as session:
        result = await session.execute(
            select(IndexedDocument.id).where(
                IndexedDocument.chunking_strategy == strategy
            )
        )
        return [row[0] for row in result.all()]


async def delete_documents_by_strategy(strategy: str) -> int:
    """Удаляет все документы с указанной стратегией. Возвращает количество удалённых."""
    async with async_session() as session:
        # Сначала получаем ID для каскадного удаления
        result = await session.execute(
            select(IndexedDocument).where(
                IndexedDocument.chunking_strategy == strategy
            )
        )
        docs = result.scalars().all()
        count = len(docs)
        for doc in docs:
            await session.delete(doc)
        await session.commit()
    return count
