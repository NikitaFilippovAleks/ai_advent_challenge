"""Pydantic-схемы для модуля индексации документов."""

from typing import Literal

from pydantic import BaseModel


# Допустимые стратегии разбиения
VALID_STRATEGIES = {"fixed_size", "structural"}

# Режимы переранжирования результатов поиска
RerankMode = Literal["none", "threshold", "keyword", "llm_cross_encoder"]


class IndexRequest(BaseModel):
    """Запрос на индексацию документов."""

    paths: list[str]
    strategy: str = "fixed_size"


class IndexResponse(BaseModel):
    """Результат индексации одного документа."""

    document_id: str
    filename: str
    chunk_count: int
    strategy: str


class SearchRequest(BaseModel):
    """Запрос на семантический поиск с опциональным переранжированием."""

    query: str
    top_k: int = 5
    # Параметры переранжирования
    rerank_mode: RerankMode = "none"
    score_threshold: float = 0.0  # минимальный порог cosine similarity
    top_k_initial: int = 20  # сколько извлечь до фильтрации
    top_k_final: int = 5  # сколько вернуть после фильтрации
    rewrite_query: bool = False  # переписать запрос через LLM


class SearchResult(BaseModel):
    """Один результат поиска — чанк с оценкой релевантности."""

    chunk_id: int
    document_id: str
    source: str
    section: str | None
    content: str
    score: float
    original_score: float | None = None  # исходный cosine similarity (до реранкинга)
    rerank_score: float | None = None  # оценка переранжирования


class SearchResponse(BaseModel):
    """Ответ семантического поиска."""

    results: list[SearchResult]
    query: str
    rewritten_query: str | None = None  # переписанный запрос (если rewrite_query=True)
    rerank_mode: str = "none"  # использованный режим переранжирования
    filtered_count: int = 0  # сколько результатов отфильтровано


class DocumentOut(BaseModel):
    """Проиндексированный документ."""

    id: str
    filename: str
    title: str
    chunking_strategy: str
    chunk_count: int
    created_at: str


class CompareRequest(BaseModel):
    """Запрос на сравнение стратегий разбиения."""

    paths: list[str]
    query: str
    top_k: int = 5


class CompareResult(BaseModel):
    """Результат одной стратегии в сравнении."""

    strategy: str
    chunk_count: int
    avg_chunk_length: float
    results: list[SearchResult]


class CompareResponse(BaseModel):
    """Сравнение двух стратегий разбиения."""

    query: str
    strategies: list[CompareResult]


class RerankCompareRequest(BaseModel):
    """Запрос на сравнение режимов переранжирования."""

    query: str
    top_k_initial: int = 20
    top_k_final: int = 5
    score_threshold: float = 0.0
    rewrite_query: bool = False


class RerankCompareResponse(BaseModel):
    """Результат сравнения режимов переранжирования."""

    query: str
    rewritten_query: str | None = None
    modes: dict[str, SearchResponse]
