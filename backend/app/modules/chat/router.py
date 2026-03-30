"""Роутер для чат-эндпоинтов.

Тонкий роутер — вся бизнес-логика в ChatService.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.modules.chat.dependencies import get_chat_service
from app.modules.chat.schemas import ChatRequest, ChatResponse
from app.modules.chat.service import ChatService

router = APIRouter()


@router.post("/api/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    service: ChatService = Depends(get_chat_service),
):
    """Отправляет сообщение и получает полный ответ."""
    try:
        return await service.process_message(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/chat/stream")
async def chat_stream(
    request: ChatRequest,
    service: ChatService = Depends(get_chat_service),
):
    """SSE-эндпоинт для стриминга ответа от LLM."""
    return StreamingResponse(
        service.process_message_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/models")
async def models(service: ChatService = Depends(get_chat_service)):
    """Возвращает список доступных моделей."""
    try:
        available = await service.get_models()
        return {"models": available}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
