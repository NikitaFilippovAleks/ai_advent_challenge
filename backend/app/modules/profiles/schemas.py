"""Pydantic-схемы для профилей пользователя."""

from pydantic import BaseModel, Field


class ProfileCreate(BaseModel):
    """Создание профиля."""
    name: str = Field(min_length=1, max_length=100)
    system_prompt: str = Field(min_length=1, max_length=10000)
    is_default: bool = False


class ProfileUpdate(BaseModel):
    """Обновление профиля (частичное)."""
    name: str | None = Field(None, min_length=1, max_length=100)
    system_prompt: str | None = Field(None, min_length=1, max_length=10000)
    is_default: bool | None = None


class ProfileOut(BaseModel):
    """Профиль в ответе API."""
    id: str
    name: str
    system_prompt: str
    is_default: bool
    created_at: str
    updated_at: str


class ConversationProfileOut(BaseModel):
    """Профиль, привязанный к диалогу, с указанием источника."""
    profile: ProfileOut | None
    source: str  # "explicit" | "default" | "none"


class SetConversationProfile(BaseModel):
    """Привязка профиля к диалогу."""
    profile_id: str | None = None  # null для сброса
