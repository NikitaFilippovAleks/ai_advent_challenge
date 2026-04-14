"""Pydantic-схемы для модуля индексации документов."""

from pydantic import BaseModel


# Допустимые стратегии разбиения
VALID_STRATEGIES = {"fixed_size", "structural"}


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
    """Запрос на семантический поиск."""

    query: str
    top_k: int = 5


class SearchResult(BaseModel):
    """Один результат поиска — чанк с оценкой релевантности."""

    chunk_id: int
    document_id: str
    source: str
    section: str | None
    content: str
    score: float


class SearchResponse(BaseModel):
    """Ответ семантического поиска."""

    results: list[SearchResult]
    query: str


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
