"""Сервис индексации документов — ядро пайплайна.

Оркестрирует: чтение файлов → chunking → генерация эмбеддингов → сохранение в БД → поиск.
"""

import hashlib
import json
import logging
import re
from collections import Counter
from pathlib import Path

import numpy as np
from gigachat import GigaChat
from gigachat.models import Messages, MessagesRole

from app.core.config import settings
from app.modules.indexing import repository
from app.modules.indexing.schemas import (
    CompareResponse,
    CompareResult,
    IndexResponse,
    RerankCompareResponse,
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

    # --- Методы реранкинга ---

    def _rerank_threshold(
        self, results: list[SearchResult], threshold: float
    ) -> list[SearchResult]:
        """Отсекает результаты с cosine similarity ниже порога."""
        return [r for r in results if r.score >= threshold]

    def _rerank_keyword(
        self, query: str, results: list[SearchResult], alpha: float = 0.5
    ) -> list[SearchResult]:
        """Переранжирует по комбинации cosine similarity и keyword overlap.

        Итоговый score = alpha * cosine + (1 - alpha) * keyword_overlap.
        keyword_overlap = доля токенов запроса, найденных в тексте чанка (Jaccard-like).
        """
        query_tokens = set(_TOKEN_RE.findall(query.lower()))
        if not query_tokens:
            return results

        reranked: list[SearchResult] = []
        for r in results:
            chunk_tokens = set(_TOKEN_RE.findall(r.content.lower()))
            # Доля токенов запроса, присутствующих в чанке
            overlap = len(query_tokens & chunk_tokens) / len(query_tokens)
            cosine = r.score
            final_score = alpha * cosine + (1 - alpha) * overlap
            reranked.append(
                r.model_copy(
                    update={
                        "original_score": round(cosine, 4),
                        "rerank_score": round(overlap, 4),
                        "score": round(final_score, 4),
                    }
                )
            )

        reranked.sort(key=lambda x: x.score, reverse=True)
        return reranked

    async def _rerank_llm(
        self, query: str, results: list[SearchResult]
    ) -> list[SearchResult]:
        """Переранжирует через LLM cross-encoder: GigaChat оценивает релевантность.

        Один вызов LLM на все чанки (батч-промпт). При ошибке — возвращает без изменений.
        """
        if not results:
            return results

        # Формируем промпт с пронумерованными чанками
        chunks_text = ""
        for i, r in enumerate(results):
            preview = r.content[:300]
            chunks_text += f"\n--- Чанк {i + 1} ---\n{preview}\n"

        prompt = (
            f"Запрос пользователя: \"{query}\"\n\n"
            f"Ниже приведены {len(results)} текстовых фрагментов. "
            "Оцени релевантность каждого фрагмента запросу по шкале от 0 до 10 "
            "(0 = совсем не релевантен, 10 = идеально релевантен).\n"
            f"{chunks_text}\n"
            "Верни ТОЛЬКО JSON-массив целых чисел в порядке фрагментов, "
            f"ровно {len(results)} элементов. Пример: [8, 3, 7, 1]"
        )

        try:
            async with self._create_client() as client:
                response = await client.achat(
                    messages=[Messages(role=MessagesRole.USER, content=prompt)]
                )
                text = response.choices[0].message.content.strip()

                # Парсим JSON-массив
                scores: list[int] = []
                try:
                    scores = json.loads(text)
                except json.JSONDecodeError:
                    # Fallback: извлекаем числа через regex
                    numbers = re.findall(r"\d+", text)
                    scores = [int(n) for n in numbers]

                if len(scores) != len(results):
                    logger.warning(
                        "LLM вернул %d оценок вместо %d, возвращаю без реранкинга",
                        len(scores),
                        len(results),
                    )
                    return results

                # Нормализуем к 0-1 и комбинируем с cosine
                reranked: list[SearchResult] = []
                for r, llm_score in zip(results, scores):
                    normalized = min(max(llm_score, 0), 10) / 10.0
                    # Итоговый score = 0.4 * cosine + 0.6 * llm_score
                    final = 0.4 * r.score + 0.6 * normalized
                    reranked.append(
                        r.model_copy(
                            update={
                                "original_score": round(r.score, 4),
                                "rerank_score": round(normalized, 4),
                                "score": round(final, 4),
                            }
                        )
                    )
                reranked.sort(key=lambda x: x.score, reverse=True)
                return reranked

        except Exception as e:
            logger.warning("Ошибка LLM-реранкинга: %s, возвращаю без изменений", e)
            return results

    async def _rewrite_query(self, query: str) -> str:
        """Переписывает поисковый запрос через LLM для улучшения извлечения."""
        prompt = (
            "Перепиши следующий поисковый запрос так, чтобы он лучше подходил "
            "для поиска по технической документации и исходному коду. "
            "Добавь ключевые термины и синонимы. "
            "Верни ТОЛЬКО переписанный запрос, без пояснений.\n\n"
            f"Запрос: {query}"
        )

        try:
            async with self._create_client() as client:
                response = await client.achat(
                    messages=[Messages(role=MessagesRole.USER, content=prompt)]
                )
                rewritten = response.choices[0].message.content.strip()
                logger.info("Запрос переписан: '%s' → '%s'", query, rewritten)
                return rewritten
        except Exception as e:
            logger.warning("Ошибка переписывания запроса: %s, используем оригинал", e)
            return query

    # --- Основной метод поиска ---

    async def search(
        self,
        query: str,
        top_k: int = 5,
        document_ids: list[str] | None = None,
        rerank_mode: str = "none",
        score_threshold: float = 0.0,
        top_k_initial: int = 20,
        top_k_final: int = 5,
        rewrite_query: bool = False,
    ) -> SearchResponse:
        """Семантический поиск по индексу с опциональным реранкингом.

        При rerank_mode != 'none':
        1. Переписывает запрос (если rewrite_query=True)
        2. Извлекает top_k_initial результатов по cosine similarity
        3. Фильтрует по score_threshold
        4. Применяет реранкинг
        5. Обрезает до top_k_final
        """
        rewritten_query: str | None = None
        search_query = query

        # Переписывание запроса через LLM
        if rewrite_query:
            search_query = await self._rewrite_query(query)
            rewritten_query = search_query

        # Генерируем эмбеддинг запроса
        query_embedding = (await self._generate_embeddings([search_query]))[0]
        query_vec = np.array(query_embedding, dtype=np.float32)

        # Загружаем все чанки
        chunks = await repository.get_all_chunks(document_ids)
        if not chunks:
            return SearchResponse(
                results=[],
                query=query,
                rewritten_query=rewritten_query,
                rerank_mode=rerank_mode,
            )

        # Вычисляем cosine similarity
        scored: list[tuple[float, dict]] = []
        for chunk in chunks:
            chunk_vec = np.array(chunk["embedding"], dtype=np.float32)
            dot = np.dot(query_vec, chunk_vec)
            norm_q = np.linalg.norm(query_vec)
            norm_c = np.linalg.norm(chunk_vec)
            if norm_q > 0 and norm_c > 0:
                score = float(dot / (norm_q * norm_c))
            else:
                score = 0.0
            scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Определяем сколько извлечь на первом этапе
        initial_limit = top_k_initial if rerank_mode != "none" else top_k
        top_results = scored[:initial_limit]

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

        # Реранкинг
        total_before = len(results)
        if rerank_mode != "none":
            # Фильтрация по порогу
            if score_threshold > 0:
                results = self._rerank_threshold(results, score_threshold)

            # Применяем реранкер
            if rerank_mode == "keyword":
                results = self._rerank_keyword(search_query, results)
            elif rerank_mode == "llm_cross_encoder":
                results = await self._rerank_llm(search_query, results)
            elif rerank_mode == "threshold":
                pass  # уже отфильтровано выше

            # Обрезаем до top_k_final
            results = results[:top_k_final]

        filtered_count = total_before - len(results)

        return SearchResponse(
            results=results,
            query=query,
            rewritten_query=rewritten_query,
            rerank_mode=rerank_mode,
            filtered_count=filtered_count,
        )

    async def compare_reranking(
        self,
        query: str,
        top_k_initial: int = 20,
        top_k_final: int = 5,
        score_threshold: float = 0.0,
        rewrite_query: bool = False,
    ) -> RerankCompareResponse:
        """Сравнивает результаты поиска с разными режимами переранжирования.

        Начальную выборку (cosine similarity) делает один раз,
        затем применяет каждый режим реранкинга отдельно.
        """
        rewritten_query: str | None = None
        search_query = query

        if rewrite_query:
            search_query = await self._rewrite_query(query)
            rewritten_query = search_query

        # Базовый поиск без реранкинга — один раз
        base_result = await self.search(
            search_query, top_k=top_k_initial, rerank_mode="none"
        )
        base_results = base_result.results

        modes: dict[str, SearchResponse] = {}

        # none — просто обрезаем до top_k_final
        modes["none"] = SearchResponse(
            results=base_results[:top_k_final],
            query=query,
            rewritten_query=rewritten_query,
            rerank_mode="none",
            filtered_count=0,
        )

        # threshold — только порог
        threshold_results = self._rerank_threshold(base_results, score_threshold)
        modes["threshold"] = SearchResponse(
            results=threshold_results[:top_k_final],
            query=query,
            rewritten_query=rewritten_query,
            rerank_mode="threshold",
            filtered_count=len(base_results) - len(threshold_results),
        )

        # keyword — порог + keyword overlap
        keyword_base = self._rerank_threshold(base_results, score_threshold)
        keyword_results = self._rerank_keyword(search_query, keyword_base)
        modes["keyword"] = SearchResponse(
            results=keyword_results[:top_k_final],
            query=query,
            rewritten_query=rewritten_query,
            rerank_mode="keyword",
            filtered_count=len(base_results) - len(keyword_base),
        )

        return RerankCompareResponse(
            query=query,
            rewritten_query=rewritten_query,
            modes=modes,
        )

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
