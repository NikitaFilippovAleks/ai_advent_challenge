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


class UsageInfo(BaseModel):
    """Информация об использовании токенов."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):
    """Ответ чата."""

    content: str
    usage: UsageInfo | None = None
