import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.context_service import build_context, extract_and_update_facts
from app.services.database import (
    add_message,
    add_message_to_branch,
    get_active_branch_id,
    get_conversation_strategy,
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
        if request.conversation_id:
            strategy = await get_conversation_strategy(request.conversation_id)
            user_msg = request.messages[-1]

            # Для branching — сохраняем в ветку если она активна
            branch_id = None
            if strategy == "branching":
                branch_id = await get_active_branch_id(request.conversation_id)

            if branch_id:
                await add_message_to_branch(
                    request.conversation_id, branch_id,
                    user_msg.role, user_msg.content,
                )
            else:
                await add_message(
                    request.conversation_id, user_msg.role, user_msg.content
                )

            # Формируем контекст по текущей стратегии
            messages = await build_context(request.conversation_id, strategy)
        else:
            messages = [m.model_dump() for m in request.messages]

        result = await get_chat_response(
            messages, model=request.model, temperature=request.temperature
        )

        # Сохраняем ответ ассистента
        if request.conversation_id:
            usage_json = None
            if result.get("usage"):
                usage_json = json.dumps(result["usage"])

            if branch_id:
                await add_message_to_branch(
                    request.conversation_id, branch_id,
                    "assistant", result["content"], usage_json,
                )
            else:
                await add_message(
                    request.conversation_id, "assistant", result["content"], usage_json
                )

            await _maybe_generate_title(
                request.conversation_id, user_msg.content, result["content"]
            )

            # Для sticky_facts — извлекаем факты после ответа
            if strategy == "sticky_facts":
                await extract_and_update_facts(
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
        user_text = request.messages[-1].content if request.messages else ""
        strategy = "summary"
        branch_id = None
        try:
            if request.conversation_id:
                strategy = await get_conversation_strategy(request.conversation_id)
                user_msg = request.messages[-1]

                # Для branching — сохраняем в ветку если активна
                if strategy == "branching":
                    branch_id = await get_active_branch_id(request.conversation_id)

                if branch_id:
                    await add_message_to_branch(
                        request.conversation_id, branch_id,
                        user_msg.role, user_msg.content,
                    )
                else:
                    await add_message(
                        request.conversation_id, user_msg.role, user_msg.content
                    )

                messages = await build_context(request.conversation_id, strategy)
            else:
                messages = [m.model_dump() for m in request.messages]

            async for event in stream_chat_response(
                messages, model=request.model, temperature=request.temperature
            ):
                event_type = event["type"]
                event_data = json.dumps(event["data"], ensure_ascii=False)

                if event_type == "delta":
                    full_response += event["data"].get("content", "")
                elif event_type == "usage":
                    usage_data = event["data"]

                yield f"event: {event_type}\ndata: {event_data}\n\n"

                # После завершения — сохраняем ответ ассистента
                if event_type == "done" and request.conversation_id:
                    usage_json = json.dumps(usage_data) if usage_data else None

                    if branch_id:
                        await add_message_to_branch(
                            request.conversation_id, branch_id,
                            "assistant", full_response, usage_json,
                        )
                    else:
                        await add_message(
                            request.conversation_id,
                            "assistant",
                            full_response,
                            usage_json,
                        )

                    await _maybe_generate_title(
                        request.conversation_id,
                        user_text,
                        full_response,
                    )

                    # Для sticky_facts — извлекаем факты после ответа
                    if strategy == "sticky_facts":
                        await extract_and_update_facts(
                            request.conversation_id,
                            user_text,
                            full_response,
                        )
        except Exception as e:
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
