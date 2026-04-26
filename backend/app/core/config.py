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

    # LM Studio (OpenAI-совместимый локальный сервер для маленьких моделей)
    # На macOS/Windows host.docker.internal резолвится автоматически,
    # на Linux нужен extra_hosts в docker-compose.yml.
    lmstudio_base_url: str = "http://host.docker.internal:1234/v1"
    lmstudio_api_key: str = "lm-studio"  # LM Studio игнорирует ключ, но openai SDK требует непустую строку
    lmstudio_default_model: str = "llama-3.2-1b-instruct"

    # Ollama (удалённый сервер с авторизацией Basic Auth)
    # Используется как альтернативный провайдер playground.
    ollama_base_url: str = "https://llm.nikfil.ru"
    ollama_username: str = ""
    ollama_password: str = ""
    ollama_default_model: str = "llama3.2:1b"

    # Управление контекстом
    context_recent_count: int = 10
    context_summary_block_size: int = 10
    context_summary_model: str = "GigaChat"

    # Память ассистента
    memory_short_term_max: int = 20  # максимум краткосрочных записей на диалог
    memory_long_term_max: int = 100  # максимум долгосрочных записей


settings = Settings()
