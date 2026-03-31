"""Сервис управления контекстом диалога.

Оркестрирует 5 стратегий формирования контекста для LLM.
"""

from app.modules.context.strategies.base import BaseContextStrategy
from app.modules.context.strategies.branching import BranchingStrategy
from app.modules.context.strategies.memory import MemoryStrategy
from app.modules.context.strategies.sliding_window import SlidingWindowStrategy
from app.modules.context.strategies.sticky_facts import StickyFactsStrategy
from app.modules.context.strategies.summary import SummaryStrategy
from app.modules.memory.service import MemoryService
from app.shared.llm.base import BaseLLMProvider


class ContextService:
    """Оркестратор стратегий контекста."""

    def __init__(self, llm: BaseLLMProvider) -> None:
        self._llm = llm
        # Стратегия sticky_facts хранится отдельно для доступа к extract_and_update_facts
        self._sticky_facts = StickyFactsStrategy(llm)
        # Сервис памяти для стратегии memory
        self._memory_service = MemoryService(llm)
        self._strategies: dict[str, BaseContextStrategy] = {
            "summary": SummaryStrategy(llm),
            "sliding_window": SlidingWindowStrategy(),
            "sticky_facts": self._sticky_facts,
            "branching": BranchingStrategy(),
            "memory": MemoryStrategy(),
        }

    async def build_context(
        self, conversation_id: str, strategy: str = "summary"
    ) -> list[dict]:
        """Формирует список сообщений для отправки в LLM в зависимости от стратегии."""
        handler = self._strategies.get(strategy, self._strategies["summary"])
        return await handler.build_context(conversation_id)

    async def extract_and_update_facts(
        self, conversation_id: str, user_text: str, assistant_text: str
    ) -> None:
        """Извлекает факты из последнего обмена (для стратегии sticky_facts)."""
        await self._sticky_facts.extract_and_update_facts(
            conversation_id, user_text, assistant_text
        )

    async def extract_memories(
        self, conversation_id: str, user_text: str, assistant_text: str
    ) -> None:
        """Извлекает и распределяет память по 3 уровням (для стратегии memory)."""
        await self._memory_service.extract_memories(
            conversation_id, user_text, assistant_text
        )
