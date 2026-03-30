"""Зависимости модуля agent для FastAPI Depends.

Заготовка — будет расширена при реализации agent loop.
"""

from functools import lru_cache

from app.modules.agent.runner import AgentRunner
from app.shared.llm.gigachat import GigaChatProvider


@lru_cache
def get_agent_runner() -> AgentRunner:
    """Создаёт и кэширует AgentRunner с GigaChatProvider."""
    llm = GigaChatProvider()
    return AgentRunner(llm=llm)
