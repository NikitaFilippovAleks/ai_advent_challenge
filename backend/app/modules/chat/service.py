"""Сервис обработки чат-сообщений.

Содержит всю бизнес-логику: сохранение сообщений, построение контекста,
вызов LLM, генерация заголовка, извлечение фактов.
"""

import json
from collections.abc import AsyncGenerator

from app.modules.chat.schemas import ChatRequest, ChatResponse
from app.modules.context.repository import get_active_branch_id, get_conversation_strategy
from app.modules.context.service import ContextService
from app.modules.conversations.repository import (
    add_message,
    add_message_to_branch,
    get_messages,
    update_conversation_title,
)
from app.shared.llm.gigachat import GigaChatProvider


class ChatService:
    """Оркестратор обработки чат-сообщений."""

    def __init__(
        self, llm: GigaChatProvider, context_service: ContextService
    ) -> None:
        self._llm = llm
        self._context = context_service

    async def process_message(self, request: ChatRequest) -> ChatResponse:
        """Обрабатывает сообщение: сохраняет, строит контекст, вызывает LLM."""
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
            messages = await self._context.build_context(
                request.conversation_id, strategy
            )
        else:
            messages = [m.model_dump() for m in request.messages]

        result = await self._llm.chat(
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

            await self._maybe_generate_title(
                request.conversation_id, user_msg.content, result["content"]
            )

            # Для sticky_facts — извлекаем факты после ответа
            if strategy == "sticky_facts":
                await self._context.extract_and_update_facts(
                    request.conversation_id, user_msg.content, result["content"]
                )

        return ChatResponse(
            content=result["content"],
            usage=result.get("usage"),
        )

    async def process_message_stream(
        self, request: ChatRequest
    ) -> AsyncGenerator[str, None]:
        """SSE-генератор: стримит ответ от LLM."""
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

                messages = await self._context.build_context(
                    request.conversation_id, strategy
                )
            else:
                messages = [m.model_dump() for m in request.messages]

            async for event in self._llm.stream(
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

                    await self._maybe_generate_title(
                        request.conversation_id,
                        user_text,
                        full_response,
                    )

                    # Для sticky_facts — извлекаем факты после ответа
                    if strategy == "sticky_facts":
                        await self._context.extract_and_update_facts(
                            request.conversation_id,
                            user_text,
                            full_response,
                        )
        except Exception as e:
            error_data = json.dumps({"message": str(e)}, ensure_ascii=False)
            yield f"event: error\ndata: {error_data}\n\n"

    async def get_models(self) -> list[dict]:
        """Возвращает список доступных моделей."""
        return await self._llm.list_models()

    async def _maybe_generate_title(
        self, conversation_id: str, user_text: str, assistant_text: str
    ) -> None:
        """Генерирует название если это первый обмен сообщениями в диалоге."""
        messages = await get_messages(conversation_id)
        # Ровно 2 сообщения — только что добавленные, первый обмен
        if len(messages) == 2:
            try:
                title = await self._llm.generate_title(user_text, assistant_text)
                await update_conversation_title(conversation_id, title)
            except Exception:
                pass  # Не критично если название не сгенерировалось
