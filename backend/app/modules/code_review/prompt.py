"""Сборка промптов для ревьюера.

Возвращает пару (system, user). Структура секций жёстко зафиксирована,
чтобы вывод можно было постить как Markdown-комментарий PR без парсинга.
"""

from app.modules.code_review.git_diff import DiffPayload
from app.modules.indexing.schemas import SearchResult


def _format_rag_snippets(snippets: list[SearchResult]) -> str:
    """Форматирует RAG-фрагменты для system-промпта."""
    if not snippets:
        return "(релевантных правил не найдено — опирайся на общие практики)"

    parts: list[str] = []
    for i, s in enumerate(snippets, 1):
        section = f" — раздел «{s.section}»" if s.section else ""
        parts.append(
            f"### Источник {i}: {s.source}{section}\n{s.content.strip()}"
        )
    return "\n\n".join(parts)


def build_review_prompt(
    diff: DiffPayload,
    rag_snippets: list[SearchResult],
) -> tuple[str, str]:
    """Формирует system и user промпты для ревью."""
    rag_block = _format_rag_snippets(rag_snippets)

    system = (
        "Ты — старший разработчик, делаешь ревью пулл-реквеста.\n"
        "Проект: GigaChat-чат на FastAPI + React, доменно-модульная архитектура.\n"
        "Отвечай на русском языке.\n\n"
        "Правила и архитектурные принципы проекта (извлечены из проектной "
        "документации через RAG):\n\n"
        f"{rag_block}\n\n"
        "Сформируй ревью строго в следующей структуре (Markdown):\n\n"
        "## Потенциальные баги\n"
        "- описание бага со ссылкой на конкретный файл/строку из diff\n"
        "- ... (если ничего не нашёл — пиши `_замечаний нет_`)\n\n"
        "## Архитектурные проблемы\n"
        "- нарушения правил проекта (с указанием правила/источника из RAG выше)\n"
        "- ... (если нарушений нет — `_замечаний нет_`)\n\n"
        "## Рекомендации\n"
        "- улучшения, упрощения, переиспользование существующих утилит проекта\n"
        "- ... (если улучшений нет — `_замечаний нет_`)\n\n"
        "Не выдумывай проблем ради заполнения секций. Если в секции пусто — "
        "так и пиши. Не добавляй других секций, заголовков и приветственных "
        "фраз — твой ответ постится как комментарий в PR."
    )

    truncation_note = ""
    if diff.truncated:
        truncation_note = (
            "\n\n**Внимание:** diff обрезан до первых 40 000 символов. "
            "Учитывай это и не делай выводов о коде, который мог быть в "
            "обрезанной части."
        )

    files_block = "\n".join(f"- {f}" for f in diff.files) if diff.files else "(нет)"

    user = (
        f"Изменённые файлы ({len(diff.files)}):\n"
        f"{files_block}\n\n"
        "Diff:\n"
        f"```diff\n{diff.diff_text}\n```"
        f"{truncation_note}"
    )

    return system, user
