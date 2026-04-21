"""Pydantic-схемы для playground-эндпоинтов."""

from pydantic import BaseModel


class PlaygroundMessage(BaseModel):
    """Одно сообщение в stateless-чате playground."""

    role: str
    content: str


class PlaygroundChatRequest(BaseModel):
    """Запрос к playground-чату.

    Вся история передаётся от фронта — бэкенд ничего не хранит.
    """

    messages: list[PlaygroundMessage]
    model: str | None = None
    temperature: float | None = 0.7
    system_prompt: str | None = None


class PlaygroundModel(BaseModel):
    """Описание модели, загруженной в LM Studio."""

    id: str
    name: str
