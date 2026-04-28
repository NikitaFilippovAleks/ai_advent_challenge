"""Сервис AI code review — оркестрация diff → RAG → LLM → markdown."""

import logging
from pathlib import Path

from app.modules.code_review.git_diff import DiffPayload, collect_diff
from app.modules.code_review.prompt import build_review_prompt
from app.modules.indexing.service import IndexingService
from app.shared.llm.gigachat import GigaChatProvider

logger = logging.getLogger(__name__)

# Имя коллекции, изолированной от пользовательских документов.
REVIEW_COLLECTION = "code_review"

# Список файлов проектной документации, по которому строится RAG.
# Пути относительные — резолвятся относительно repo_root.
PROJECT_DOC_PATHS = [
    ".claude/CLAUDE.md",
    ".claude/rules/architecture.md",
    ".claude/rules/code-style.md",
    ".claude/rules/stack.md",
    "README.md",
]

# Сообщение, возвращаемое CLI, когда в PR нет изменений.
EMPTY_DIFF_MESSAGE = "_В PR нет изменений для ревью._"


class CodeReviewService:
    """Координирует сбор diff, поиск релевантных правил в RAG и вызов LLM."""

    def __init__(
        self,
        indexing_service: IndexingService,
        llm: GigaChatProvider,
    ) -> None:
        self._indexing = indexing_service
        self._llm = llm

    async def _ensure_index(self, repo_root: str) -> None:
        """Переиндексирует проектную документацию для коллекции code_review.

        Каждый запуск пересобирает индекс с нуля (replace_collection=True).
        Документов мало — занимает секунды, зато всегда свежий.
        """
        # Резолвим пути и оставляем только существующие файлы
        resolved: list[str] = []
        for rel in PROJECT_DOC_PATHS:
            full = Path(repo_root) / rel
            if full.exists() and full.is_file():
                resolved.append(str(full))
            else:
                logger.info("Пропуск (файл не найден): %s", full)

        if not resolved:
            logger.warning(
                "Не найдено ни одного файла документации для индексации — "
                "ревью будет без проектного контекста"
            )
            return

        await self._indexing.index_documents(
            paths=resolved,
            strategy_name="structural",
            collection=REVIEW_COLLECTION,
            replace_collection=True,
        )

    def _build_search_query(self, diff: DiffPayload) -> str:
        """Формирует запрос для поиска релевантных правил по PR.

        Список изменённых файлов + начало diff'а — этого хватает эмбеддеру,
        чтобы найти секции про затронутые слои/модули.
        """
        files_str = ", ".join(diff.files) if diff.files else "(нет)"
        diff_preview = diff.diff_text[:800]
        return f"Изменены файлы: {files_str}. Diff: {diff_preview}"

    async def review(self, base: str, head: str, repo_root: str) -> str:
        """Главная точка: собирает diff, готовит контекст и возвращает Markdown-ревью."""
        diff = collect_diff(base=base, head=head, repo_root=repo_root)

        # Раннее завершение для пустого PR
        if not diff.files or not diff.diff_text.strip():
            logger.info("Пустой diff — пропускаем вызов LLM")
            return EMPTY_DIFF_MESSAGE

        await self._ensure_index(repo_root)

        # Поиск релевантных правил
        search = await self._indexing.search(
            query=self._build_search_query(diff),
            rerank_mode="keyword",
            top_k_initial=20,
            top_k_final=6,
            score_threshold=0.15,
            collection=REVIEW_COLLECTION,
        )
        snippets = search.results
        logger.info("Найдено RAG-фрагментов: %d", len(snippets))

        # Сборка промпта и вызов LLM
        system, user = build_review_prompt(diff=diff, rag_snippets=snippets)

        response = await self._llm.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
        )

        content = response.get("content", "").strip()
        if not content:
            raise RuntimeError("LLM вернул пустой ответ")

        return content
