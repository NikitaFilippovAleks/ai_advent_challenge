"""Зависимости модуля agent для FastAPI Depends."""

from functools import lru_cache

from app.modules.agent.mcp_manager import MCPManager
from app.modules.agent.runner import AgentRunner
from app.shared.llm.gigachat import GigaChatProvider


@lru_cache
def get_mcp_manager() -> MCPManager:
    """Создаёт и кэширует singleton MCPManager."""
    return MCPManager()


@lru_cache
def get_agent_runner() -> AgentRunner:
    """Создаёт и кэширует AgentRunner с GigaChatProvider и MCPManager."""
    llm = GigaChatProvider()
    mcp = get_mcp_manager()
    return AgentRunner(llm=llm, mcp_manager=mcp)
