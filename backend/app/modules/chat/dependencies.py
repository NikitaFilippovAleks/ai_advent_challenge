"""Зависимости модуля chat для FastAPI Depends.

Это единственное место, где разрешён кросс-модульный импорт —
для сборки ChatService с его зависимостями.
"""

from functools import lru_cache

from app.modules.chat.service import ChatService
from app.modules.context.service import ContextService
from app.modules.profiles.repository import get_default_profile, get_profile
from app.shared.llm.gigachat import GigaChatProvider


@lru_cache
def get_chat_service() -> ChatService:
    """Создаёт и кэширует ChatService с GigaChatProvider и ContextService."""
    llm = GigaChatProvider()
    context_service = ContextService(llm=llm)
    return ChatService(
        llm=llm,
        context_service=context_service,
        get_profile_fn=get_profile,
        get_default_profile_fn=get_default_profile,
    )
