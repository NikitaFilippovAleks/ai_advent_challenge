"""Сервис обработки чат-сообщений.

Содержит всю бизнес-логику: сохранение сообщений, построение контекста,
вызов LLM, генерация заголовка, извлечение фактов и памяти.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Callable, Awaitable

logger = logging.getLogger(__name__)

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

    # Маппинг категорий инвариантов на русские названия
    _CATEGORY_LABELS = {
        "architecture": "АРХИТЕКТУРА",
        "technical": "ТЕХНИЧЕСКИЕ РЕШЕНИЯ",
        "stack": "СТЕК",
        "business": "БИЗНЕС-ПРАВИЛА",
    }

    def __init__(
        self,
        llm: GigaChatProvider,
        context_service: ContextService,
        get_profile_fn: Callable[[str], Awaitable[dict | None]] | None = None,
        get_default_profile_fn: Callable[[], Awaitable[dict | None]] | None = None,
        get_active_invariants_fn: Callable[[], Awaitable[list[dict]]] | None = None,
        task_service=None,
    ) -> None:
        self._llm = llm
        self._context = context_service
        self._get_profile = get_profile_fn
        self._get_default_profile = get_default_profile_fn
        self._get_active_invariants = get_active_invariants_fn
        self._task_service = task_service

    async def _get_system_prompt(self, conversation_id: str) -> str | None:
        """Получает system prompt из профиля диалога (явного или дефолтного)."""
        if not self._get_profile or not self._get_default_profile:
            return None

        from app.core.database import async_session
        from app.models import Conversation as ConvModel

        async with async_session() as session:
            conv = await session.get(ConvModel, conversation_id)
        if conv is None:
            return None

        profile = None
        if conv.profile_id:
            profile = await self._get_profile(conv.profile_id)
        if profile is None:
            profile = await self._get_default_profile()

        if profile:
            return profile["system_prompt"]
        return None

    async def _build_invariants_text(self) -> str | None:
        """Формирует текст инвариантов для включения в system prompt."""
        if not self._get_active_invariants:
            return None

        invariants = await self._get_active_invariants()
        if not invariants:
            return None

        # Формируем список инвариантов с категориями
        lines = []
        for inv in invariants:
            label = self._CATEGORY_LABELS.get(inv["category"], inv["category"].upper())
            lines.append(f"[{label}] {inv['name']}: {inv['description']}")

        invariants_text = "\n".join(lines)

        return (
            "ИНВАРИАНТЫ (ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА):\n"
            "Ниже перечислены инварианты — правила, которые ты ОБЯЗАН соблюдать в каждом ответе.\n"
            "Если запрос пользователя конфликтует с любым инвариантом, ты ДОЛЖЕН:\n"
            "1. Отказать в выполнении запроса\n"
            "2. Явно указать, какой инвариант нарушается (название и описание)\n"
            "3. Объяснить, почему это нарушение\n"
            "4. Предложить альтернативу в рамках инвариантов\n\n"
            f"{invariants_text}"
        )

    async def _build_task_prompt(self, conversation_id: str, user_text: str) -> tuple[str | None, dict | None]:
        """Возвращает (task_system_prompt, active_task) или (None, None).

        Если активной задачи нет — классифицирует сообщение.
        При classification='task' создаёт задачу.
        """
        if not self._task_service:
            return None, None

        active_task = await self._task_service.get_active(conversation_id)

        if not active_task:
            msg_type = await self._task_service.classify_message(user_text)
            if msg_type == "task":
                # Используем первые 100 символов как название задачи
                title = user_text[:100].strip()
                active_task = await self._task_service.create(conversation_id, title)
            else:
                return None, None

        # Обрабатываем сообщение пользователя для автопереходов
        # (например, "да" при готовом плане → execution)
        updated = await self._task_service.process_user_message(active_task, user_text)
        if updated:
            active_task = updated

        prompt = self._task_service.build_system_prompt(active_task)
        return prompt, active_task

    def _merge_system_messages(self, messages: list[dict]) -> list[dict]:
        """Объединяет все system-сообщения в одно первое (требование GigaChat API)."""
        system_parts = []
        other_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_parts.append(msg["content"])
            else:
                other_messages.append(msg)

        if not system_parts:
            return other_messages

        merged = {"role": "system", "content": "\n\n".join(system_parts)}
        return [merged] + other_messages

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
            # Подставляем system prompt из профиля (перед сообщениями пользователя)
            system_prompt = await self._get_system_prompt(request.conversation_id)
            if system_prompt:
                messages.insert(0, {"role": "system", "content": system_prompt})
            # Инварианты — наивысший приоритет, вставляем первым system-блоком
            invariants_text = await self._build_invariants_text()
            if invariants_text:
                messages.insert(0, {"role": "system", "content": invariants_text})
            # Задачи — промпт текущей фазы FSM
            task_prompt, active_task = await self._build_task_prompt(
                request.conversation_id, user_msg.content
            )
            if task_prompt:
                # Вставляем после всех system-сообщений
                sys_count = len([m for m in messages if m["role"] == "system"])
                messages.insert(sys_count, {"role": "system", "content": task_prompt})
            # GigaChat требует ровно одно system-сообщение первым — объединяем
            messages = self._merge_system_messages(messages)
        else:
            messages = [m.model_dump() for m in request.messages]
            active_task = None

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

            # Память работает ВСЕГДА — запускаем фоновую задачу (не блокируем ответ)
            asyncio.create_task(
                self._extract_memories_safe(
                    request.conversation_id, user_msg.content, result["content"]
                )
            )

            # Обработка FSM — автоматические переходы
            if self._task_service and active_task:
                await self._task_service.process_llm_response(
                    active_task, result["content"]
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
                # Подставляем system prompt из профиля (перед сообщениями пользователя)
                system_prompt = await self._get_system_prompt(request.conversation_id)
                if system_prompt:
                    messages.insert(0, {"role": "system", "content": system_prompt})
                # Инварианты — наивысший приоритет, вставляем первым system-блоком
                invariants_text = await self._build_invariants_text()
                if invariants_text:
                    messages.insert(0, {"role": "system", "content": invariants_text})
                # Задачи — промпт текущей фазы FSM
                task_prompt, active_task = await self._build_task_prompt(
                    request.conversation_id, user_text
                )
                if task_prompt:
                    sys_count = len([m for m in messages if m["role"] == "system"])
                    messages.insert(sys_count, {"role": "system", "content": task_prompt})
                # GigaChat требует ровно одно system-сообщение первым — объединяем
                messages = self._merge_system_messages(messages)
            else:
                messages = [m.model_dump() for m in request.messages]
                active_task = None

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

            # Всё post-processing — в фоновой задаче, чтобы генератор завершился
            # и StreamingResponse закрыл соединение сразу после done event
            if request.conversation_id and full_response:
                asyncio.create_task(
                    self._post_stream_processing(
                        request.conversation_id, strategy, branch_id,
                        user_text, full_response, usage_data,
                        active_task=active_task if "active_task" in locals() else None,
                    )
                )
        except Exception as e:
            error_data = json.dumps({"message": str(e)}, ensure_ascii=False)
            yield f"event: error\ndata: {error_data}\n\n"

    async def get_models(self) -> list[dict]:
        """Возвращает список доступных моделей."""
        return await self._llm.list_models()

    async def _post_stream_processing(
        self, conversation_id: str, strategy: str, branch_id: int | None,
        user_text: str, full_response: str, usage_data: dict | None,
        active_task: dict | None = None,
    ) -> None:
        """Фоновая задача: сохранение ответа, заголовок, факты, память.

        Вынесено из генератора чтобы SSE-соединение закрывалось сразу после done.
        """
        try:
            # Сохраняем ответ ассистента в БД
            usage_json = json.dumps(usage_data) if usage_data else None
            if branch_id:
                await add_message_to_branch(
                    conversation_id, branch_id,
                    "assistant", full_response, usage_json,
                )
            else:
                await add_message(
                    conversation_id, "assistant", full_response, usage_json,
                )

            # Генерация заголовка
            await self._maybe_generate_title(conversation_id, user_text, full_response)

            # Извлечение фактов (для sticky_facts)
            if strategy == "sticky_facts":
                await self._context.extract_and_update_facts(
                    conversation_id, user_text, full_response,
                )

            # Память — всегда
            await self._context.extract_memories(
                conversation_id, user_text, full_response,
            )

            # Обработка FSM — автоматические переходы
            if self._task_service and active_task:
                await self._task_service.process_llm_response(
                    active_task, full_response
                )
        except Exception as e:
            logger.error("Фоновый post-processing упал: %s", e, exc_info=True)

    async def _extract_memories_safe(
        self, conversation_id: str, user_text: str, assistant_text: str
    ) -> None:
        """Безопасно извлекает память в фоне. Ошибки не влияют на основной поток."""
        try:
            await self._context.extract_memories(
                conversation_id, user_text, assistant_text
            )
        except Exception as e:
            logger.error("Фоновое извлечение памяти упало: %s", e, exc_info=True)

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
