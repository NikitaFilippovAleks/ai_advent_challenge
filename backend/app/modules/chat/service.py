"""Сервис обработки чат-сообщений.

Содержит всю бизнес-логику: сохранение сообщений, построение контекста,
вызов LLM, генерация заголовка, извлечение фактов и памяти.
"""

import asyncio
import json
import logging
import re
from collections.abc import AsyncGenerator, Callable, Awaitable

# Токенайзер для keyword-реранкинга (буквы/цифры, по аналогии с indexing/service)
_TOKEN_RE = re.compile(r"[\w\-]+", re.UNICODE)

logger = logging.getLogger(__name__)

from app.modules.agent.runner import AgentRunner
from app.modules.chat.schemas import ChatRequest, ChatResponse
from app.modules.indexing.service import IndexingService
from app.modules.context.repository import get_active_branch_id, get_conversation_strategy
from app.modules.context.service import ContextService
from app.modules.conversations.repository import (
    add_message,
    add_message_to_branch,
    get_messages,
    update_conversation_title,
)
from app.modules.memory.repository import (
    get_insights,
    get_working_memory,
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
        agent_runner: AgentRunner | None = None,
        indexing_service: IndexingService | None = None,
    ) -> None:
        self._llm = llm
        self._context = context_service
        self._get_profile = get_profile_fn
        self._get_default_profile = get_default_profile_fn
        self._get_active_invariants = get_active_invariants_fn
        self._task_service = task_service
        self._agent = agent_runner
        self._indexing = indexing_service

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

    # Порог релевантности: если лучший score ниже — режим "не знаю".
    # Значение подобрано под эмбеддинги GigaChat — на русских текстах
    # cosine similarity редко превышает 0.3 даже для очень релевантных чанков.
    LOW_RELEVANCE_THRESHOLD = 0.15

    def _keyword_rerank(self, query: str, results: list, alpha: float = 0.3):
        """Реранкинг по ОРИГИНАЛЬНОМУ короткому запросу.

        Отличается от indexing._rerank_keyword тем, что использует
        короткий query без контекста — это даёт максимальный вес
        точным совпадениям ("Vue", "MongoDB", "Meilisearch").
        alpha=0.3 → keyword-overlap важнее, чем cosine similarity.
        """
        query_tokens = set(t.lower() for t in _TOKEN_RE.findall(query) if len(t) > 2)
        if not query_tokens:
            return results

        reranked = []
        for r in results:
            chunk_tokens = set(t.lower() for t in _TOKEN_RE.findall(r.content))
            overlap = len(query_tokens & chunk_tokens) / len(query_tokens)
            cosine = r.score
            final_score = alpha * cosine + (1 - alpha) * overlap
            reranked.append(
                r.model_copy(update={
                    "original_score": round(cosine, 4),
                    "rerank_score": round(overlap, 4),
                    "score": round(final_score, 4),
                })
            )
        reranked.sort(key=lambda x: x.score, reverse=True)
        return reranked

    def _enrich_query_with_context(
        self, query: str, history: list[dict] | None
    ) -> str:
        """Обогащает короткий follow-up-запрос контекстом предыдущих сообщений.

        Эмбеддер плохо ищет по коротким вопросам типа «Vue можно?» —
        без темы диалога они не находят релевантные чанки. Склеиваем
        последние 3 пользовательские реплики + последний ответ ассистента
        в один более «жирный» query-текст. Источники при этом не меняются.
        """
        if not history:
            return query

        # Берём до 3 предыдущих пользовательских сообщений (кроме текущего)
        prev_user_texts = [
            m["content"] for m in history
            if m.get("role") == "user" and m.get("content")
        ][-4:-1]  # до 3 предыдущих

        last_assistant = next(
            (m["content"] for m in reversed(history)
             if m.get("role") == "assistant" and m.get("content")),
            None,
        )

        parts: list[str] = []
        for text in prev_user_texts:
            parts.append(text[:200])
        if last_assistant:
            parts.append(last_assistant[:400])
        # Текущий вопрос дублируем 2 раза — чтобы он доминировал в эмбеддинге
        parts.append(query)
        parts.append(query)

        return " | ".join(parts)

    async def _build_rag_context(
        self,
        query: str,
        rerank_mode: str = "keyword",
        score_threshold: float = 0.1,
        history: list[dict] | None = None,
    ) -> tuple[str | None, list[dict], bool]:
        """Ищет релевантные чанки и формирует RAG-контекст с переранжированием.

        Возвращает (system_message_text, sources_list, is_low_relevance)
        или (None, [], False) если поиск пуст.
        """
        if not self._indexing:
            return None, [], False

        search_query = self._enrich_query_with_context(query, history)

        # Двухэтапный поиск:
        # 1) эмбеддер работает по обогащённому query (context-aware)
        # 2) keyword-rerank работает по ОРИГИНАЛЬНОМУ короткому query,
        #    чтобы "Vue"/"MongoDB" не размывались контекстом.
        search_result = await self._indexing.search(
            search_query,
            top_k=30,
            rerank_mode="none",
            score_threshold=0.0,
            top_k_initial=30,
            top_k_final=30,
        )
        # Применяем keyword-реранкинг по исходному короткому запросу
        if search_result.results and rerank_mode == "keyword":
            search_result.results = self._keyword_rerank(
                query, search_result.results
            )[:8]
        else:
            search_result.results = search_result.results[:8]
        if not search_result.results:
            return None, [], False

        # Формируем список источников для SSE-события
        sources = [
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
            for r in search_result.results
        ]

        # Проверяем релевантность: если лучший score ниже порога — режим "не знаю"
        max_score = max(r.score for r in search_result.results)
        is_low_relevance = max_score < self.LOW_RELEVANCE_THRESHOLD

        if is_low_relevance:
            low_relevance_prompt = (
                "Контекст из базы знаний имеет очень низкую релевантность к вопросу пользователя. "
                "Ответь СТРОГО: «К сожалению, в имеющихся документах я не нашёл достаточно "
                "релевантной информации по вашему вопросу. Пожалуйста, уточните запрос или "
                "переформулируйте вопрос.» НЕ пытайся отвечать на основе общих знаний."
            )
            return low_relevance_prompt, sources, True

        # Формируем текст для system prompt с обязательными цитатами
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
        for i, r in enumerate(search_result.results, 1):
            section_info = f", секция: {r.section}" if r.section else ""
            parts.append(f"--- Источник {i} [файл: {r.source}{section_info}] ---")
            parts.append(r.content)
            parts.append("")

        return "\n".join(parts), sources, False

    # Приоритет категорий рабочей памяти при выводе в промпт
    _WORKING_CATEGORY_ORDER = ["goal", "constraint", "decision", "result", "fact"]
    _WORKING_CATEGORY_LABELS = {
        "goal": "ЦЕЛЬ ДИАЛОГА",
        "constraint": "ОГРАНИЧЕНИЯ / ТЕРМИНЫ",
        "decision": "ПРИНЯТЫЕ РЕШЕНИЯ",
        "result": "ПРОМЕЖУТОЧНЫЕ РЕЗУЛЬТАТЫ",
        "fact": "УТОЧНЁННЫЕ ФАКТЫ",
    }

    async def _build_task_memory_text(self, conversation_id: str) -> str | None:
        """Формирует блок «Память задачи» для system prompt.

        Собирает рабочую память (goal/constraint/decision/result/fact)
        и последние краткосрочные наблюдения. Используется всегда —
        даже при стратегии summary и при включённом RAG, чтобы ассистент
        не терял цель и зафиксированные ограничения в длинных диалогах.
        """
        try:
            working = await get_working_memory(conversation_id)
            insights = await get_insights(conversation_id)
        except Exception as e:
            logger.warning("Не удалось загрузить память задачи: %s", e)
            return None

        if not working and not insights:
            return None

        # Группируем рабочую память по категориям
        by_category: dict[str, list[dict]] = {}
        for item in working:
            by_category.setdefault(item["category"], []).append(item)

        parts = ["ПАМЯТЬ ЗАДАЧИ (не теряй это в ответе):"]

        for cat in self._WORKING_CATEGORY_ORDER:
            items = by_category.get(cat)
            if not items:
                continue
            label = self._WORKING_CATEGORY_LABELS.get(cat, cat.upper())
            parts.append(f"\n{label}:")
            for it in items:
                parts.append(f"  - {it['key']}: {it['value']}")

        # Последние 5 наблюдений — даёт модели «текущий фокус» диалога
        if insights:
            recent = insights[-5:]
            parts.append("\nНЕДАВНИЕ НАБЛЮДЕНИЯ ПО ДИАЛОГУ:")
            for ins in recent:
                parts.append(f"  - {ins['content']}")

        parts.append(
            "\nИспользуй эту память как устойчивый контекст задачи. "
            "Не противоречь зафиксированным целям и ограничениям. "
            "Если пользователь меняет цель/ограничение — подтверди изменение явно."
        )

        return "\n".join(parts)

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
            # RAG — вставляем контекст из индексированных документов
            if request.use_rag:
                rag_text, _rag_sources, _low_rel = await self._build_rag_context(
                    user_msg.content,
                    rerank_mode=request.rag_rerank_mode,
                    score_threshold=request.rag_score_threshold,
                    history=messages,
                )
                if rag_text:
                    messages.insert(
                        len([m for m in messages if m["role"] == "system"]),
                        {"role": "system", "content": rag_text},
                    )
            # Память задачи — goal/constraints/decisions + недавние наблюдения.
            # Инжектим всегда, независимо от стратегии, чтобы в длинных
            # диалогах ассистент не терял цель и зафиксированные ограничения.
            task_memory_text = await self._build_task_memory_text(request.conversation_id)
            if task_memory_text:
                sys_count = len([m for m in messages if m["role"] == "system"])
                messages.insert(sys_count, {"role": "system", "content": task_memory_text})
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

        # При включённом RAG — обходим AgentRunner, чтобы LLM не дёргала
        # MCP-инструменты (search_files и т.п.) вместо ответа из переданного
        # RAG-контекста. Чистый RAG-режим: только документы из индекса.
        use_agent = self._agent and not request.use_rag
        if use_agent:
            result = await self._agent.run(
                messages, model=request.model, temperature=request.temperature
            )
        else:
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
                # RAG — вставляем контекст и запоминаем источники
                rag_sources = []
                is_low_relevance = False
                if request.use_rag:
                    rag_text, rag_sources, is_low_relevance = await self._build_rag_context(
                        user_text,
                        rerank_mode=request.rag_rerank_mode,
                        score_threshold=request.rag_score_threshold,
                        history=messages,
                    )
                    if rag_text:
                        messages.insert(
                            len([m for m in messages if m["role"] == "system"]),
                            {"role": "system", "content": rag_text},
                        )
                # Память задачи — goal/constraints/decisions + недавние наблюдения.
                # Инжектим всегда, чтобы ассистент не терял цель в длинных диалогах.
                task_memory_text = await self._build_task_memory_text(
                    request.conversation_id
                )
                if task_memory_text:
                    sys_count = len([m for m in messages if m["role"] == "system"])
                    messages.insert(
                        sys_count, {"role": "system", "content": task_memory_text}
                    )
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
                rag_sources = []

            # Отправляем SSE-событие sources до начала генерации
            if request.use_rag and rag_sources:
                sources_data = json.dumps(
                    {"sources": rag_sources, "low_relevance": is_low_relevance},
                    ensure_ascii=False,
                )
                yield f"event: sources\ndata: {sources_data}\n\n"

            # При включённом RAG — обходим AgentRunner, чтобы LLM не дёргала
            # MCP-инструменты вместо ответа из RAG-контекста.
            use_agent_stream = self._agent and not request.use_rag
            stream_source = (
                self._agent.run_stream(messages, model=request.model, temperature=request.temperature)
                if use_agent_stream
                else self._llm.stream(messages, model=request.model, temperature=request.temperature)
            )
            async for event in stream_source:
                event_type = event["type"]
                event_data = json.dumps(event["data"], ensure_ascii=False)

                if event_type == "delta":
                    full_response += event["data"].get("content", "")
                elif event_type == "usage":
                    usage_data = event["data"]

                # Пробрасываем все события включая tool_call и tool_result
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
