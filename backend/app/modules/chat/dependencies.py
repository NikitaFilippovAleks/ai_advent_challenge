"""Зависимости модуля chat для FastAPI Depends.

Это единственное место, где разрешён кросс-модульный импорт —
для сборки ChatService с его зависимостями.
"""

from functools import lru_cache

from app.modules.agent.dependencies import get_agent_runner
from app.modules.chat.service import ChatService
from app.modules.indexing.dependencies import get_indexing_service
from app.modules.context.service import ContextService
from app.modules.invariants.repository import get_active_invariants
from app.modules.profiles.repository import get_default_profile, get_profile
from app.modules.tasks.service import TaskService
from app.shared.llm.gigachat import GigaChatProvider


@lru_cache
def get_chat_service() -> ChatService:
    """Создаёт и кэширует ChatService с GigaChatProvider, ContextService и AgentRunner."""
    llm = GigaChatProvider()
    context_service = ContextService(llm=llm)
    task_service = TaskService(llm=llm)
    agent_runner = get_agent_runner()
    indexing_service = get_indexing_service()
    return ChatService(
        llm=llm,
        context_service=context_service,
        get_profile_fn=get_profile,
        get_default_profile_fn=get_default_profile,
        get_active_invariants_fn=get_active_invariants,
        task_service=task_service,
        agent_runner=agent_runner,
        indexing_service=indexing_service,
    )
