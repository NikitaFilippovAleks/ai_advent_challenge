"""Конфигурация приложения через переменные окружения.

Использует pydantic-settings для автоматической загрузки из .env файла.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки приложения, загружаемые из переменных окружения."""

    # GigaChat
    gigachat_credentials: str = ""
    gigachat_verify_ssl: bool = False
    gigachat_model: str = "GigaChat"

    # Управление контекстом
    context_recent_count: int = 10
    context_summary_block_size: int = 10
    context_summary_model: str = "GigaChat"

    # Память ассистента
    memory_short_term_max: int = 20  # максимум краткосрочных записей на диалог
    memory_long_term_max: int = 100  # максимум долгосрочных записей


settings = Settings()
