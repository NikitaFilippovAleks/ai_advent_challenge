"""Роутер playground — stateless чат с LM Studio.

Без БД, без контекстных стратегий, без памяти, без агента.
RAG поддерживается опционально: если use_rag=True, перед вызовом LLM
выполняется поиск по локальному индексу и найденный контекст
инжектируется в начало messages как system-сообщение (та же логика,
что в основном чате — см. app/modules/indexing/rag_context.py).
"""

import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.modules.indexing.rag_context import build_rag_context
from app.modules.indexing.service import IndexingService
from app.modules.playground.dependencies import (
    get_indexing_service_dep,
    get_lmstudio_provider,
)
from app.modules.playground.schemas import PlaygroundChatRequest
from app.shared.llm.lmstudio import LMStudioProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/playground", tags=["playground"])


def _sse_event(event: str, data: dict) -> str:
    """Сериализует событие в формат Server-Sent Events."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _base_messages(request: PlaygroundChatRequest) -> list[dict]:
    """История от клиента + опциональный user-level system prompt."""
    messages: list[dict] = []
    if request.system_prompt:
        messages.append({"role": "system", "content": request.system_prompt})
    messages.extend({"role": m.role, "content": m.content} for m in request.messages)
    return messages


async def _apply_rag(
    request: PlaygroundChatRequest, indexing: IndexingService
) -> tuple[list[dict], list[dict], bool]:
    """Собирает messages с RAG-контекстом и список источников.

    Возвращает (messages, sources, is_low_relevance).
    Если RAG отключён или не нашёл ничего — sources=[], messages без изменений.
    """
    messages = _base_messages(request)

    if not request.use_rag or not request.messages:
        return messages, [], False

    # Последний user-запрос — то, по чему делаем retrieval.
    last_user = next(
        (m.content for m in reversed(request.messages) if m.role == "user"), None
    )
    if not last_user:
        return messages, [], False

    rag_text, sources, is_low_relevance = await build_rag_context(
        indexing_service=indexing,
        query=last_user,
        history=messages,
        rerank_mode=request.rag_rerank_mode,
        score_threshold=request.rag_score_threshold,
        top_k_final=request.rag_top_k or 8,
    )

    if rag_text:
        # Вставляем RAG-контекст после существующих system-сообщений,
        # чтобы инструкции RAG доминировали над общим system prompt.
        sys_count = sum(1 for m in messages if m["role"] == "system")
        messages.insert(sys_count, {"role": "system", "content": rag_text})

    return messages, sources, is_low_relevance


@router.get("/models")
async def list_models(
    provider: LMStudioProvider = Depends(get_lmstudio_provider),
):
    """Список моделей, доступных в локальном LM Studio."""
    try:
        models = await provider.list_models()
        return {"models": models}
    except Exception as e:
        logger.warning("LM Studio недоступен: %s", e)
        # Не считаем это 500 — UI должен показать осмысленное сообщение
        raise HTTPException(
            status_code=503,
            detail=(
                "Не удалось подключиться к LM Studio. "
                "Убедись, что локальный сервер запущен и модель загружена."
            ),
        )


@router.post("/chat/stream")
async def chat_stream(
    request: PlaygroundChatRequest,
    provider: LMStudioProvider = Depends(get_lmstudio_provider),
    indexing: IndexingService = Depends(get_indexing_service_dep),
):
    """SSE-стриминг ответа от локальной модели с опциональным RAG."""
    try:
        messages, sources, is_low_relevance = await _apply_rag(request, indexing)
    except Exception as e:
        logger.exception("Ошибка подготовки RAG-контекста в playground")
        raise HTTPException(status_code=500, detail=f"RAG: {e}")

    async def generator() -> AsyncGenerator[str, None]:
        try:
            # Событие sources — до первого delta, чтобы фронт мог показать
            # панель источников одновременно с началом генерации ответа.
            if request.use_rag and sources:
                yield _sse_event(
                    "sources",
                    {"sources": sources, "low_relevance": is_low_relevance},
                )

            async for event in provider.stream(
                messages=messages,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            ):
                yield _sse_event(event["type"], event["data"])
        except Exception as e:
            logger.exception("Ошибка стриминга LM Studio")
            yield _sse_event("error", {"message": str(e)})

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat")
async def chat(
    request: PlaygroundChatRequest,
    provider: LMStudioProvider = Depends(get_lmstudio_provider),
    indexing: IndexingService = Depends(get_indexing_service_dep),
):
    """Нестримовый вариант — на случай отладки."""
    try:
        messages, sources, is_low_relevance = await _apply_rag(request, indexing)
        result = await provider.chat(
            messages=messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        # Возвращаем источники рядом с ответом — удобно для ручной отладки.
        if request.use_rag:
            result = {
                **result,
                "sources": sources,
                "low_relevance": is_low_relevance,
            }
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
