"""Построение RAG-контекста для вставки в system prompt LLM.

Вынесено из ChatService, чтобы основной чат (GigaChat) и playground (LM Studio)
могли использовать одну и ту же логику сборки источников и промптов.

Публичная функция: build_rag_context(...). Возвращает готовый текст
system-сообщения, список источников и флаг низкой релевантности.
"""

from __future__ import annotations

import re

from app.modules.indexing.schemas import SearchResult
from app.modules.indexing.service import IndexingService

# Токенайзер для keyword-реранкинга (слова/числа, кириллица/латиница).
_TOKEN_RE = re.compile(r"[\w\-]+", re.UNICODE)

# Если лучший score ниже порога — режим «не знаю».
# Значение подобрано под эмбеддинги GigaChat — на русских текстах
# cosine similarity редко превышает 0.3 даже для очень релевантных чанков.
LOW_RELEVANCE_THRESHOLD = 0.15


def keyword_rerank(
    query: str, results: list[SearchResult], alpha: float = 0.3
) -> list[SearchResult]:
    """Реранкинг по ОРИГИНАЛЬНОМУ короткому запросу.

    Использует короткий query без контекста — это даёт максимальный
    вес точным совпадениям (например, «Vue», «MongoDB»).
    alpha=0.3 → keyword-overlap важнее cosine similarity.
    """
    query_tokens = {t.lower() for t in _TOKEN_RE.findall(query) if len(t) > 2}
    if not query_tokens:
        return results

    reranked: list[SearchResult] = []
    for r in results:
        chunk_tokens = {t.lower() for t in _TOKEN_RE.findall(r.content)}
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


def enrich_query_with_context(
    query: str, history: list[dict] | None
) -> str:
    """Обогащает короткий follow-up-запрос контекстом предыдущих сообщений.

    Эмбеддер плохо ищет по коротким вопросам типа «Vue можно?»: без темы
    диалога они не находят релевантные чанки. Склеиваем последние 3
    пользовательские реплики и последний ответ ассистента в один более
    «жирный» query-текст. Источники при этом не меняются.
    """
    if not history:
        return query

    # До 3 предыдущих пользовательских сообщений (кроме текущего).
    prev_user_texts = [
        m["content"]
        for m in history
        if m.get("role") == "user" and m.get("content")
    ][-4:-1]

    last_assistant = next(
        (
            m["content"]
            for m in reversed(history)
            if m.get("role") == "assistant" and m.get("content")
        ),
        None,
    )

    parts: list[str] = [text[:200] for text in prev_user_texts]
    if last_assistant:
        parts.append(last_assistant[:400])
    # Текущий вопрос дублируем дважды — чтобы он доминировал в эмбеддинге.
    parts.append(query)
    parts.append(query)

    return " | ".join(parts)


def _format_sources(results: list[SearchResult]) -> list[dict]:
    """Преобразует SearchResult → dict для SSE-события sources."""
    return [
        {
            "chunk_id": r.chunk_id,
            "document_id": r.document_id,
            "source": r.source,
            "section": r.section,
            "content": r.content[:200],
            "score": r.score,
            "original_score": r.original_score,
            "rerank_score": r.rerank_score,
        }
        for r in results
    ]


def _format_system_prompt(results: list[SearchResult]) -> str:
    """Собирает system-текст с инструкциями и цитатами источников."""
    parts = [
        "ПРАВИЛА ОТВЕТА С ИСТОЧНИКАМИ (ОБЯЗАТЕЛЬНЫ):",
        "",
        "1. ВНИМАТЕЛЬНО прочитай все источники ниже перед ответом.",
        "2. Отвечай ТОЛЬКО на основе предоставленных источников ниже — "
        "НЕ добавляй информацию из общих знаний, НЕ придумывай, НЕ делай "
        "предположений «исходя из общей практики».",
        "3. Если в источниках есть прямой запрет (слова «запрещено», "
        "«нельзя», «не разрешено» и т.п.) — ответ должен быть категоричным "
        "«запрещено/нельзя», с дословной цитатой. Запрещено смягчать или "
        "интерпретировать запреты как «рекомендации».",
        "4. В ответе ОБЯЗАТЕЛЬНО:",
        "   - Прямой ответ на вопрос (одно предложение)",
        "   - Дословная цитата из источника в формате: > «цитата» — [Источник N]",
        "   - В конце — **Источники:** [Источник N] файл: ..., секция: ...",
        "5. Если источники НЕ содержат информации для ответа — ответь СТРОГО:",
        '   «К сожалению, в имеющихся документах я не нашёл информации по вашему вопросу. '
        'Пожалуйста, уточните запрос или переформулируйте вопрос.»',
        "   НЕ пытайся отвечать на основе общих знаний.",
        "6. НЕ вызывай никакие инструменты (tool-calls) — ответ строй только "
        "из текста источников ниже.",
        "",
    ]
    for i, r in enumerate(results, 1):
        section_info = f", секция: {r.section}" if r.section else ""
        parts.append(f"--- Источник {i} [файл: {r.source}{section_info}] ---")
        parts.append(r.content)
        parts.append("")
    return "\n".join(parts)


async def build_rag_context(
    *,
    indexing_service: IndexingService,
    query: str,
    history: list[dict] | None = None,
    rerank_mode: str | None = "keyword",
    score_threshold: float | None = None,  # не используется, оставлено для совместимости
    top_k_final: int = 8,
) -> tuple[str | None, list[dict], bool]:
    """Ищет релевантные чанки и формирует RAG-контекст с переранжированием.

    Возвращает (system_message_text, sources_list, is_low_relevance)
    или (None, [], False), если поиск пуст.

    Двухэтапная схема:
    1) эмбеддер работает по обогащённому query (context-aware);
    2) keyword-rerank работает по ОРИГИНАЛЬНОМУ короткому query,
       чтобы точные термины не размывались контекстом.
    """
    del score_threshold  # параметр зарезервирован, реального применения нет
    search_query = enrich_query_with_context(query, history)

    search_result = await indexing_service.search(
        search_query,
        top_k=30,
        rerank_mode="none",
        score_threshold=0.0,
        top_k_initial=30,
        top_k_final=30,
    )

    if search_result.results and rerank_mode == "keyword":
        search_result.results = keyword_rerank(query, search_result.results)[:top_k_final]
    else:
        search_result.results = search_result.results[:top_k_final]

    if not search_result.results:
        return None, [], False

    sources = _format_sources(search_result.results)

    max_score = max(r.score for r in search_result.results)
    is_low_relevance = max_score < LOW_RELEVANCE_THRESHOLD

    if is_low_relevance:
        low_relevance_prompt = (
            "Контекст из базы знаний имеет очень низкую релевантность к вопросу пользователя. "
            "Ответь СТРОГО: «К сожалению, в имеющихся документах я не нашёл достаточно "
            "релевантной информации по вашему вопросу. Пожалуйста, уточните запрос или "
            "переформулируйте вопрос.» НЕ пытайся отвечать на основе общих знаний."
        )
        return low_relevance_prompt, sources, True

    return _format_system_prompt(search_result.results), sources, False
