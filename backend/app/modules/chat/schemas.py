"""Pydantic-схемы для модуля chat."""

from pydantic import BaseModel


class MessageItem(BaseModel):
    """Одно сообщение в запросе чата."""

    role: str
    content: str


class ChatRequest(BaseModel):
    """Запрос на отправку сообщения в чат."""

    messages: list[MessageItem]
    model: str | None = None
    temperature: float | None = None
    conversation_id: str | None = None
    use_rag: bool = False
    rag_rerank_mode: str = "keyword"  # режим переранжирования RAG-результатов
    rag_score_threshold: float = 0.1  # порог отсечения нерелевантных результатов
    # /help-режим: использовать RAG по project_docs + инжектить git-ветку
    # в system prompt, не отключая MCP-tools (агент + RAG работают вместе).
    help_mode: bool = False
    # Логическая коллекция RAG (project_docs для /help, default для остального).
    rag_collection: str | None = None
    # Дополнение к system prompt от пресета слеш-команды на фронте.
    system_prompt_addon: str | None = None


class UsageInfo(BaseModel):
    """Информация об использовании токенов."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):
    """Ответ чата."""

    content: str
    usage: UsageInfo | None = None
