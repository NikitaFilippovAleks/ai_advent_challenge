"""Оценка качества RAG — 10 контрольных вопросов по документации проекта.

Каждый вопрос прогоняется дважды: с RAG и без RAG.
Сравниваются найденные ключевые слова в ответах LLM.

Запуск: docker compose exec backend python -m pytest tests/rag_evaluation.py -v -s
"""

import asyncio
from dataclasses import dataclass

import pytest
import pytest_asyncio

from app.core.database import init_db
from app.modules.chat.schemas import ChatRequest, MessageItem
from app.modules.chat.service import ChatService
from app.modules.context.service import ContextService
from app.modules.indexing.service import IndexingService
from app.shared.llm.gigachat import GigaChatProvider

# Пути к документам внутри Docker-контейнера
DOCS_TO_INDEX = [
    "/app/CLAUDE.md",
    "/app/.claude/rules/architecture.md",
    "/app/.claude/rules/code-style.md",
    "/app/.claude/rules/stack.md",
]


@dataclass
class ControlQuestion:
    """Контрольный вопрос для оценки RAG."""

    question: str  # Текст вопроса
    expected_keywords: list[str]  # Ключевые слова, ожидаемые в ответе
    expected_sources: list[str]  # Файлы-источники, откуда должен прийти ответ


# 10 контрольных вопросов по документации проекта
CONTROL_QUESTIONS = [
    ControlQuestion(
        question="Какой веб-фреймворк используется на бэкенде?",
        expected_keywords=["FastAPI"],
        expected_sources=["CLAUDE.md"],
    ),
    ControlQuestion(
        question="Какие стратегии управления контекстом поддерживаются?",
        expected_keywords=["summary", "sliding_window", "sticky_facts", "branching", "memory"],
        expected_sources=["CLAUDE.md"],
    ),
    ControlQuestion(
        question="Какой SDK используется для работы с LLM?",
        expected_keywords=["gigachat", "GigaChat"],
        expected_sources=["CLAUDE.md"],
    ),
    ControlQuestion(
        question="Как запустить проект в Docker?",
        expected_keywords=["docker", "compose", "make"],
        expected_sources=["CLAUDE.md"],
    ),
    ControlQuestion(
        question="Какие MCP-серверы зарегистрированы в проекте?",
        expected_keywords=["git", "scheduler", "research", "system", "notes"],
        expected_sources=["CLAUDE.md"],
    ),
    ControlQuestion(
        question="Что такое инварианты в этом проекте?",
        expected_keywords=["правил", "инвариант", "обязан"],
        expected_sources=["CLAUDE.md"],
    ),
    ControlQuestion(
        question="Какие категории инвариантов существуют?",
        expected_keywords=["architecture", "technical", "stack", "business"],
        expected_sources=["CLAUDE.md"],
    ),
    ControlQuestion(
        question="Как устроена доменно-модульная архитектура бэкенда?",
        expected_keywords=["core", "shared", "modules"],
        expected_sources=["architecture.md"],
    ),
    ControlQuestion(
        question="Какие слои есть в архитектуре и как они связаны?",
        expected_keywords=["core", "shared", "modules", "импорт"],
        expected_sources=["architecture.md"],
    ),
    ControlQuestion(
        question="Какой линтер используется в Python-коде проекта?",
        expected_keywords=["ruff"],
        expected_sources=["code-style.md"],
    ),
]


def _check_keywords(text: str, keywords: list[str]) -> list[str]:
    """Проверяет наличие ключевых слов в тексте (без учёта регистра).

    Возвращает список найденных ключевых слов.
    """
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


# --- Фикстуры ---


@pytest.fixture(scope="module")
def event_loop():
    """Создаёт единый event loop для всего модуля (нужен для module-scoped async фикстур)."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="module")
async def indexing_service() -> IndexingService:
    """Сервис индексации — синглтон на весь модуль тестов."""
    return IndexingService()


@pytest_asyncio.fixture(scope="module")
async def chat_service(indexing_service: IndexingService) -> ChatService:
    """Сервис чата с подключённым RAG, без агента/профилей/инвариантов/задач."""
    llm = GigaChatProvider()
    context_service = ContextService(llm)
    return ChatService(
        llm=llm,
        context_service=context_service,
        indexing_service=indexing_service,
    )


@pytest_asyncio.fixture(scope="module", autouse=True)
async def index_documents(indexing_service: IndexingService):
    """Инициализирует БД и индексирует документы перед запуском тестов."""
    await init_db()
    results = await indexing_service.index_documents(DOCS_TO_INDEX, "structural")
    print(f"\n{'=' * 60}")
    print("ИНДЕКСАЦИЯ ДОКУМЕНТОВ")
    print(f"{'=' * 60}")
    for r in results:
        print(f"  {r.filename} — {r.chunk_count} чанков (стратегия: {r.strategy})")
    print(f"{'=' * 60}\n")


# --- Параметризованный тест ---


@pytest.mark.parametrize(
    "question_data",
    CONTROL_QUESTIONS,
    ids=[f"q{i+1}" for i in range(len(CONTROL_QUESTIONS))],
)
@pytest.mark.asyncio
async def test_rag_comparison(
    question_data: ControlQuestion,
    chat_service: ChatService,
):
    """Сравнивает ответы LLM с RAG и без RAG на контрольный вопрос."""
    question = question_data.question
    keywords = question_data.expected_keywords
    sources = question_data.expected_sources

    print(f"\n{'─' * 60}")
    print(f"ВОПРОС: {question}")
    print(f"Ожидаемые ключевые слова: {keywords}")
    print(f"Ожидаемые источники: {sources}")
    print(f"{'─' * 60}")

    # --- Запрос БЕЗ RAG ---
    request_no_rag = ChatRequest(
        messages=[MessageItem(role="user", content=question)],
        use_rag=False,
    )
    response_no_rag = await chat_service.process_message(request_no_rag)
    found_no_rag = _check_keywords(response_no_rag.content, keywords)

    print(f"\n  [БЕЗ RAG]")
    print(f"  Ответ: {response_no_rag.content[:300]}...")
    print(f"  Найдено ключевых слов: {len(found_no_rag)}/{len(keywords)} — {found_no_rag}")

    # --- Запрос С RAG ---
    request_with_rag = ChatRequest(
        messages=[MessageItem(role="user", content=question)],
        use_rag=True,
    )
    response_with_rag = await chat_service.process_message(request_with_rag)
    found_with_rag = _check_keywords(response_with_rag.content, keywords)

    print(f"\n  [С RAG]")
    print(f"  Ответ: {response_with_rag.content[:300]}...")
    print(f"  Найдено ключевых слов: {len(found_with_rag)}/{len(keywords)} — {found_with_rag}")

    # --- Сравнительная таблица ---
    print(f"\n  {'Метрика':<30} {'Без RAG':<20} {'С RAG':<20}")
    print(f"  {'─' * 70}")
    print(f"  {'Ключевых слов найдено':<30} {len(found_no_rag):<20} {len(found_with_rag):<20}")
    print(f"  {'Длина ответа (символов)':<30} {len(response_no_rag.content):<20} {len(response_with_rag.content):<20}")

    # Предупреждение если RAG не нашёл ни одного ключевого слова
    if len(found_with_rag) == 0:
        print(f"\n  ⚠ ВНИМАНИЕ: RAG не нашёл ни одного ключевого слова в ответе!")

    # Не assert-им на количество — LLM недетерминистичен
    # Тест всегда проходит, результаты оцениваются визуально
