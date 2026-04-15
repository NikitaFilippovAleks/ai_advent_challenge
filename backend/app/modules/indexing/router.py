"""API-эндпоинты для индексации документов и семантического поиска."""

from fastapi import APIRouter, Depends, HTTPException

from app.modules.indexing.dependencies import get_indexing_service
from app.modules.indexing.schemas import (
    VALID_STRATEGIES,
    CompareRequest,
    CompareResponse,
    DocumentOut,
    IndexRequest,
    IndexResponse,
    RerankCompareRequest,
    RerankCompareResponse,
    SearchRequest,
    SearchResponse,
)
from app.modules.indexing.service import IndexingService
from app.modules.indexing import repository

router = APIRouter()


@router.post("/api/indexing/index", response_model=list[IndexResponse])
async def index_documents(
    request: IndexRequest,
    service: IndexingService = Depends(get_indexing_service),
):
    """Индексирует документы: разбивает на чанки, генерирует эмбеддинги, сохраняет."""
    if request.strategy not in VALID_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"Неизвестная стратегия: {request.strategy}. "
            f"Допустимые: {', '.join(VALID_STRATEGIES)}",
        )
    return await service.index_documents(request.paths, request.strategy)


@router.post("/api/indexing/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    service: IndexingService = Depends(get_indexing_service),
):
    """Семантический поиск по проиндексированным документам с опциональным реранкингом."""
    return await service.search(
        query=request.query,
        top_k=request.top_k,
        rerank_mode=request.rerank_mode,
        score_threshold=request.score_threshold,
        top_k_initial=request.top_k_initial,
        top_k_final=request.top_k_final,
        rewrite_query=request.rewrite_query,
    )


@router.get("/api/indexing/documents", response_model=list[DocumentOut])
async def list_documents():
    """Возвращает список проиндексированных документов."""
    docs = await repository.get_all_documents()
    return docs


@router.get("/api/indexing/documents/{doc_id}", response_model=DocumentOut)
async def get_document(doc_id: str):
    """Возвращает детали проиндексированного документа."""
    doc = await repository.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Документ не найден")
    return doc


@router.delete("/api/indexing/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Удаляет проиндексированный документ и все его чанки."""
    deleted = await repository.delete_document(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Документ не найден")
    return {"status": "deleted", "document_id": doc_id}


@router.post("/api/indexing/rerank-compare", response_model=RerankCompareResponse)
async def compare_reranking(
    request: RerankCompareRequest,
    service: IndexingService = Depends(get_indexing_service),
):
    """Сравнивает результаты поиска с разными режимами переранжирования."""
    return await service.compare_reranking(
        query=request.query,
        top_k_initial=request.top_k_initial,
        top_k_final=request.top_k_final,
        score_threshold=request.score_threshold,
        rewrite_query=request.rewrite_query,
    )


@router.post("/api/indexing/compare", response_model=CompareResponse)
async def compare_strategies(
    request: CompareRequest,
    service: IndexingService = Depends(get_indexing_service),
):
    """Сравнивает две стратегии разбиения на одних документах."""
    return await service.compare_strategies(
        request.paths, request.query, request.top_k
    )
