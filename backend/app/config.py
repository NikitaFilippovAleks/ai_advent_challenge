from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gigachat_credentials: str = ""
    gigachat_verify_ssl: bool = False
    gigachat_model: str = "GigaChat"

    # Управление контекстом: суммаризация старых сообщений
    # Количество последних сообщений, которые отправляются как есть
    context_recent_count: int = 10
    # Размер блока сообщений для одной суммаризации
    context_summary_block_size: int = 10
    # Модель для суммаризации
    context_summary_model: str = "GigaChat"


settings = Settings()
