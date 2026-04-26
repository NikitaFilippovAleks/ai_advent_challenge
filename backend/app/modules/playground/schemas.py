"""Pydantic-схемы для playground-эндпоинтов."""

from typing import Literal

from pydantic import BaseModel

from app.modules.indexing.schemas import RerankMode

PlaygroundProvider = Literal["lmstudio", "ollama"]


class PlaygroundMessage(BaseModel):
    """Одно сообщение в stateless-чате playground."""

    role: str
    content: str


class PlaygroundChatRequest(BaseModel):
    """Запрос к playground-чату.

    Вся история передаётся от фронта — бэкенд ничего не хранит.
    """

    messages: list[PlaygroundMessage]
    # Провайдер: локальный LM Studio или удалённый Ollama. Дефолт сохраняет старое поведение.
    provider: PlaygroundProvider = "lmstudio"
    model: str | None = None
    temperature: float | None = 0.7
    system_prompt: str | None = None
    # Лимит токенов ответа. Если None — используется дефолт провайдера (2048).
    # Нужен для сравнительного playground: оптимизированный подчат обрезает
    # длинные ответы, чтобы модель не уходила в рассуждения.
    max_tokens: int | None = None

    # RAG-параметры. Если use_rag=False — поиск не выполняется, поведение
    # playground остаётся прежним (чистая модель без внешнего контекста).
    use_rag: bool = False
    rag_rerank_mode: RerankMode | None = "keyword"
    rag_score_threshold: float | None = None
    rag_top_k: int | None = 8


class PlaygroundModel(BaseModel):
    """Описание модели, загруженной в LM Studio."""

    id: str
    name: str
