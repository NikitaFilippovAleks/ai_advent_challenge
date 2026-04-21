"""Зависимости playground-модуля: синглтон LMStudioProvider."""

from functools import lru_cache

from app.shared.llm.lmstudio import LMStudioProvider


@lru_cache
def get_lmstudio_provider() -> LMStudioProvider:
    """Возвращает закэшированный провайдер LM Studio."""
    return LMStudioProvider()
