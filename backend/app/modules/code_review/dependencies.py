"""DI-фабрики для модуля code_review.

Единственное место, где допустим кросс-модульный импорт (правило проекта).
"""

from functools import lru_cache

from app.modules.code_review.service import CodeReviewService
from app.modules.indexing.dependencies import get_indexing_service
from app.shared.llm.gigachat import GigaChatProvider


@lru_cache
def get_gigachat_provider() -> GigaChatProvider:
    """Закэшированный синглтон GigaChat-провайдера."""
    return GigaChatProvider()


@lru_cache
def get_code_review_service() -> CodeReviewService:
    """Собирает CodeReviewService из существующих зависимостей."""
    return CodeReviewService(
        indexing_service=get_indexing_service(),
        llm=get_gigachat_provider(),
    )
