import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.database import (
    add_message,
    get_messages,
    update_conversation_title,
)
from app.services.gigachat_service import (
    generate_title,
    get_available_models,
    get_chat_response,
    stream_chat_response,
)

router = APIRouter()


class MessageItem(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[MessageItem]
    model: str | None = None
    temperature: float | None = None
    conversation_id: str | None = None


class UsageInfo(BaseModel):
    """Информация об использовании токенов."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):
    content: str
    usage: UsageInfo | None = None


async def _maybe_generate_title(
    conversation_id: str, user_text: str, assistant_text: str
) -> None:
    """Генерирует название если это первый обмен сообщениями в диалоге."""
    messages = await get_messages(conversation_id)
    # Ровно 2 сообщения — только что добавленные, первый обмен
    if len(messages) == 2:
        try:
            title = await generate_title(user_text, assistant_text)
            await update_conversation_title(conversation_id, title)
        except Exception:
            pass  # Не критично если название не сгенерировалось


@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        messages = [m.model_dump() for m in request.messages]
        result = await get_chat_response(
            messages, model=request.model, temperature=request.temperature
        )

        # Сохраняем сообщения в БД если указан conversation_id
        if request.conversation_id:
            user_msg = request.messages[-1]
            await add_message(
                request.conversation_id, user_msg.role, user_msg.content
            )
            usage_json = None
            if result.get("usage"):
                usage_json = json.dumps(result["usage"])
            await add_message(
                request.conversation_id, "assistant", result["content"], usage_json
            )
            await _maybe_generate_title(
                request.conversation_id, user_msg.content, result["content"]
            )

        return ChatResponse(
            content=result["content"],
            usage=result.get("usage"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """SSE-эндпоинт для стриминга ответа от GigaChat."""

    async def event_generator():
        full_response = ""
        usage_data = None
        try:
            messages = [m.model_dump() for m in request.messages]
            async for event in stream_chat_response(
                messages, model=request.model, temperature=request.temperature
            ):
                event_type = event["type"]
                event_data = json.dumps(event["data"], ensure_ascii=False)

                # Собираем полный ответ и usage для сохранения
                if event_type == "delta":
                    full_response += event["data"].get("content", "")
                elif event_type == "usage":
                    usage_data = event["data"]

                yield f"event: {event_type}\ndata: {event_data}\n\n"

                # После завершения — сохраняем в БД
                if event_type == "done" and request.conversation_id:
                    user_msg = request.messages[-1]
                    await add_message(
                        request.conversation_id, user_msg.role, user_msg.content
                    )
                    usage_json = json.dumps(usage_data) if usage_data else None
                    await add_message(
                        request.conversation_id,
                        "assistant",
                        full_response,
                        usage_json,
                    )
                    await _maybe_generate_title(
                        request.conversation_id,
                        user_msg.content,
                        full_response,
                    )
        except Exception as e:
            # Отправляем ошибку как SSE-событие
            error_data = json.dumps({"message": str(e)}, ensure_ascii=False)
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/models")
async def models():
    try:
        available = await get_available_models()
        return {"models": available}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
