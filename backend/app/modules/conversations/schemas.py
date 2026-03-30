"""Pydantic-схемы для модуля conversations."""

from pydantic import BaseModel


class ConversationOut(BaseModel):
    """Диалог в ответе API."""

    id: str
    title: str
    updated_at: str


class MessageOut(BaseModel):
    """Сообщение в ответе API."""

    id: int | None = None
    role: str
    content: str
    usage: dict | None = None
    created_at: str
