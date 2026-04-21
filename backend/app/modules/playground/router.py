"""Роутер playground — stateless чат с LM Studio.

Без БД, без контекстных стратегий, без памяти, без RAG, без агента.
Вся история приходит от клиента в каждом запросе.
"""

import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.modules.playground.dependencies import get_lmstudio_provider
from app.modules.playground.schemas import PlaygroundChatRequest
from app.shared.llm.lmstudio import LMStudioProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/playground", tags=["playground"])


def _sse_event(event: str, data: dict) -> str:
    """Сериализует событие в формат Server-Sent Events."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_messages(request: PlaygroundChatRequest) -> list[dict]:
    """Собирает итоговый список сообщений: system prompt (если задан) + история."""
    messages: list[dict] = []
    if request.system_prompt:
        messages.append({"role": "system", "content": request.system_prompt})
    messages.extend({"role": m.role, "content": m.content} for m in request.messages)
    return messages


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
):
    """SSE-стриминг ответа от локальной модели."""
    messages = _build_messages(request)

    async def generator() -> AsyncGenerator[str, None]:
        try:
            async for event in provider.stream(
                messages=messages,
                model=request.model,
                temperature=request.temperature,
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
):
    """Нестримовый вариант — на случай отладки."""
    try:
        return await provider.chat(
            messages=_build_messages(request),
            model=request.model,
            temperature=request.temperature,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
