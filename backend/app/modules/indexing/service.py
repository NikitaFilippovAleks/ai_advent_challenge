"""Сервис индексации документов — ядро пайплайна.

Оркестрирует: чтение файлов → chunking → генерация эмбеддингов → сохранение в БД → поиск.
"""

import hashlib
import logging
import re
from collections import Counter
from pathlib import Path

import numpy as np
from gigachat import GigaChat

from app.core.config import settings
from app.modules.indexing import repository
from app.modules.indexing.schemas import (
    CompareResponse,
    CompareResult,
    IndexResponse,
    SearchResponse,
    SearchResult,
)
from app.modules.indexing.strategies.base import BaseChunkingStrategy
from app.modules.indexing.strategies.fixed_size import FixedSizeStrategy
from app.modules.indexing.strategies.structural import StructuralStrategy

logger = logging.getLogger(__name__)

# Размер батча для генерации эмбеддингов через GigaChat
EMBEDDING_BATCH_SIZE = 10

# Размерность вектора для локальных эмбеддингов (feature hashing)
LOCAL_EMBEDDING_DIM = 256

# Регулярка для токенизации текста (слова + числа)
_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9_]+")


def _local_embedding(text: str) -> list[float]:
    """Генерирует эмбеддинг через feature hashing (bag-of-words + n-грамм).

    Детерминистический метод: каждое слово/биграмм хешируется в фиксированный
    вектор размерности LOCAL_EMBEDDING_DIM. Не требует внешних API.
    """
    tokens = _TOKEN_RE.findall(text.lower())
    if not tokens:
        return [0.0] * LOCAL_EMBEDDING_DIM

    # Униграммы + биграммы для лучшего захвата контекста
    features: list[str] = list(tokens)
    for i in range(len(tokens) - 1):
        features.append(f"{tokens[i]}_{tokens[i + 1]}")

    vec = np.zeros(LOCAL_EMBEDDING_DIM, dtype=np.float64)
    counts = Counter(features)
    for feature, count in counts.items():
        # Feature hashing: хеш слова → индекс в векторе
        h = int(hashlib.md5(feature.encode("utf-8")).hexdigest(), 16)
        idx = h % LOCAL_EMBEDDING_DIM
        # Знак определяет направление (+1 или -1) для уменьшения коллизий
        sign = 1.0 if (h // LOCAL_EMBEDDING_DIM) % 2 == 0 else -1.0
        vec[idx] += sign * count

    # L2-нормализация
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm

    return vec.tolist()


class IndexingService:
    """Сервис индексации: chunking → embedding → хранение → поиск."""

    def __init__(self) -> None:
        self._strategies: dict[str, BaseChunkingStrategy] = {
            "fixed_size": FixedSizeStrategy(),
            "structural": StructuralStrategy(),
        }
        self._use_gigachat_embeddings: bool | None = None

    def _create_client(self) -> GigaChat:
        """Создаёт клиент GigaChat для генерации эмбеддингов."""
        return GigaChat(
            credentials=settings.gigachat_credentials,
            verify_ssl_certs=settings.gigachat_verify_ssl,
        )

    async def _generate_embeddings_gigachat(self, texts: list[str]) -> list[list[float]]:
        """Генерирует эмбеддинги через GigaChat SDK батчами."""
        all_embeddings: list[list[float]] = []

        async with self._create_client() as client:
            for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
                batch = texts[i : i + EMBEDDING_BATCH_SIZE]
                response = await client.aembeddings(texts=batch, model="Embeddings")
                for item in response.data:
                    all_embeddings.append(item.embedding)
                logger.info(
                    "GigaChat эмбеддингов: %d/%d",
                    len(all_embeddings),
                    len(texts),
                )

        return all_embeddings

    def _generate_embeddings_local(self, texts: list[str]) -> list[list[float]]:
        """Генерирует эмбеддинги локально через feature hashing."""
        embeddings = [_local_embedding(text) for text in texts]
        logger.info("Локальных эмбеддингов: %d", len(embeddings))
        return embeddings

    async def _generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Генерирует эмбеддинги: пробует GigaChat, при ошибке — локальный fallback."""
        # Если уже знаем что GigaChat недоступен — сразу локальный
        if self._use_gigachat_embeddings is False:
            return self._generate_embeddings_local(texts)

        # Первая попытка — пробуем GigaChat
        if self._use_gigachat_embeddings is None:
            try:
                result = await self._generate_embeddings_gigachat(texts[:1])
                self._use_gigachat_embeddings = True
                logger.info("GigaChat Embeddings API доступен")
                # Дополучим остальные
                if len(texts) > 1:
                    rest = await self._generate_embeddings_gigachat(texts[1:])
                    result.extend(rest)
                return result
            except Exception as e:
                logger.warning(
                    "GigaChat Embeddings недоступен (%s), переключаюсь на локальные", e
                )
                self._use_gigachat_embeddings = False
                return self._generate_embeddings_local(texts)

        # GigaChat доступен — используем
        return await self._generate_embeddings_gigachat(texts)

    def _read_file(self, path: str) -> str | None:
        """Читает содержимое файла, возвращает None если файл не найден."""
        p = Path(path)
        if not p.exists() or not p.is_file():
            logger.warning("Файл не найден: %s", path)
            return None
        return p.read_text(encoding="utf-8", errors="replace")

    def _content_hash(self, content: str) -> str:
        """Вычисляет SHA-256 хеш содержимого."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    async def index_documents(
        self, paths: list[str], strategy_name: str = "fixed_size"
    ) -> list[IndexResponse]:
        """Индексирует документы: читает, чанкит, генерирует эмбеддинги, сохраняет."""
        strategy = self._strategies.get(strategy_name)
        if strategy is None:
            raise ValueError(f"Неизвестная стратегия: {strategy_name}")

        results: list[IndexResponse] = []

        for path in paths:
            content = self._read_file(path)
            if content is None:
                continue

            content_hash = self._content_hash(content)

            # Пропускаем если уже проиндексировано с тем же хешем и стратегией
            existing = await repository.find_document_by_hash(
                content_hash, strategy_name
            )
            if existing:
                logger.info("Пропуск (уже проиндексирован): %s", path)
                results.append(
                    IndexResponse(
                        document_id=existing["id"],
                        filename=path,
                        chunk_count=existing["chunk_count"],
                        strategy=strategy_name,
                    )
                )
                continue

            # Разбиваем на чанки
            chunks = strategy.chunk(content, path)
            if not chunks:
                logger.warning("Нет чанков для файла: %s", path)
                continue

            # Генерируем эмбеддинги
            texts = [c.content for c in chunks]
            embeddings = await self._generate_embeddings(texts)

            # Определяем title из имени файла
            title = Path(path).name

            # Сохраняем документ
            doc = await repository.save_document(
                filename=path,
                title=title,
                content_hash=content_hash,
                strategy=strategy_name,
                chunk_count=len(chunks),
            )

            # Сохраняем чанки с эмбеддингами
            chunk_dicts = [
                {
                    "chunk_index": c.chunk_index,
                    "content": c.content,
                    "embedding": embeddings[i],
                    "source": path,
                    "section": c.section,
                    "char_start": c.char_start,
                    "char_end": c.char_end,
                }
                for i, c in enumerate(chunks)
            ]
            await repository.save_chunks(doc["id"], chunk_dicts)

            logger.info(
                "Проиндексирован: %s (%d чанков, стратегия: %s)",
                path,
                len(chunks),
                strategy_name,
            )

            results.append(
                IndexResponse(
                    document_id=doc["id"],
                    filename=path,
                    chunk_count=len(chunks),
                    strategy=strategy_name,
                )
            )

        return results

    async def search(
        self,
        query: str,
        top_k: int = 5,
        document_ids: list[str] | None = None,
    ) -> SearchResponse:
        """Семантический поиск по индексу: эмбеддинг запроса → cosine similarity."""
        # Генерируем эмбеддинг запроса
        query_embedding = (await self._generate_embeddings([query]))[0]
        query_vec = np.array(query_embedding, dtype=np.float32)

        # Загружаем все чанки
        chunks = await repository.get_all_chunks(document_ids)
        if not chunks:
            return SearchResponse(results=[], query=query)

        # Вычисляем cosine similarity
        scored: list[tuple[float, dict]] = []
        for chunk in chunks:
            chunk_vec = np.array(chunk["embedding"], dtype=np.float32)
            # cosine similarity = dot(a, b) / (norm(a) * norm(b))
            dot = np.dot(query_vec, chunk_vec)
            norm_q = np.linalg.norm(query_vec)
            norm_c = np.linalg.norm(chunk_vec)
            if norm_q > 0 and norm_c > 0:
                score = float(dot / (norm_q * norm_c))
            else:
                score = 0.0
            scored.append((score, chunk))

        # Сортируем по убыванию и берём top_k
        scored.sort(key=lambda x: x[0], reverse=True)
        top_results = scored[:top_k]

        results = [
            SearchResult(
                chunk_id=chunk["id"],
                document_id=chunk["document_id"],
                source=chunk["source"],
                section=chunk["section"],
                content=chunk["content"],
                score=round(score, 4),
            )
            for score, chunk in top_results
        ]

        return SearchResponse(results=results, query=query)

    async def compare_strategies(
        self, paths: list[str], query: str, top_k: int = 5
    ) -> CompareResponse:
        """Сравнивает две стратегии разбиения на одних документах."""
        strategy_results: list[CompareResult] = []

        for strategy_name in ["fixed_size", "structural"]:
            # Индексируем файлы выбранной стратегией
            index_results = await self.index_documents(paths, strategy_name)

            # Собираем ID документов этой стратегии
            doc_ids = [r.document_id for r in index_results]

            # Считаем общее количество чанков и среднюю длину
            all_chunks = await repository.get_all_chunks(doc_ids)
            total_chunks = len(all_chunks)
            avg_length = (
                sum(len(c["content"]) for c in all_chunks) / total_chunks
                if total_chunks > 0
                else 0.0
            )

            # Поиск по чанкам этой стратегии
            search_result = await self.search(query, top_k, doc_ids)

            strategy_results.append(
                CompareResult(
                    strategy=strategy_name,
                    chunk_count=total_chunks,
                    avg_chunk_length=round(avg_length, 1),
                    results=search_result.results,
                )
            )

        return CompareResponse(query=query, strategies=strategy_results)
