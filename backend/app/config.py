from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gigachat_credentials: str = ""
    gigachat_verify_ssl: bool = False
    gigachat_model: str = "GigaChat"


settings = Settings()
