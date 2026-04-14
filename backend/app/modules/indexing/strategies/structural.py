"""Стратегия структурного разбиения текста по заголовкам, определениям и абзацам."""

import re

from app.modules.indexing.strategies.base import BaseChunkingStrategy, ChunkResult
from app.modules.indexing.strategies.fixed_size import FixedSizeStrategy


# Максимальный размер чанка — если больше, дробим через fixed_size
MAX_CHUNK_SIZE = 1500

# Fallback-стратегия для слишком больших чанков
_fallback = FixedSizeStrategy(chunk_size=MAX_CHUNK_SIZE, overlap=150)


class StructuralStrategy(BaseChunkingStrategy):
    """Разбиение по структуре документа.

    - Markdown (.md): по заголовкам (#, ##, ###)
    - Python (.py): по top-level определениям (class, def, async def)
    - Прочие: по двойным переносам строк (абзацы)

    Если чанк превышает MAX_CHUNK_SIZE — дробит его fixed_size стратегией.
    """

    @property
    def name(self) -> str:
        return "structural"

    def chunk(self, text: str, source: str) -> list[ChunkResult]:
        """Определяет тип документа и применяет соответствующее разбиение."""
        if not text.strip():
            return []

        if source.endswith(".md"):
            raw_chunks = self._split_markdown(text)
        elif source.endswith(".py"):
            raw_chunks = self._split_python(text)
        else:
            raw_chunks = self._split_paragraphs(text)

        # Пост-обработка: дробим слишком большие чанки
        result: list[ChunkResult] = []
        index = 0
        for section, content, char_start, char_end in raw_chunks:
            if len(content) > MAX_CHUNK_SIZE:
                # Разбиваем большой чанк fixed_size стратегией
                sub_chunks = _fallback.chunk(content, source)
                for sc in sub_chunks:
                    result.append(ChunkResult(
                        content=sc.content,
                        chunk_index=index,
                        section=section,
                        char_start=char_start + sc.char_start,
                        char_end=char_start + sc.char_end,
                    ))
                    index += 1
            else:
                stripped = content.strip()
                if stripped:
                    result.append(ChunkResult(
                        content=stripped,
                        chunk_index=index,
                        section=section,
                        char_start=char_start,
                        char_end=char_end,
                    ))
                    index += 1

        return result

    def _split_markdown(self, text: str) -> list[tuple[str | None, str, int, int]]:
        """Разбивает Markdown по заголовкам (# ## ###)."""
        # Паттерн: строка начинается с # (1-3 уровня)
        pattern = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
        matches = list(pattern.finditer(text))

        if not matches:
            return self._split_paragraphs(text)

        chunks: list[tuple[str | None, str, int, int]] = []

        # Текст до первого заголовка (если есть)
        if matches[0].start() > 0:
            preamble = text[: matches[0].start()]
            if preamble.strip():
                chunks.append((None, preamble, 0, matches[0].start()))

        # Каждый заголовок + текст до следующего заголовка
        for i, match in enumerate(matches):
            section_name = match.group(2).strip()
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end]
            if content.strip():
                chunks.append((section_name, content, start, end))

        return chunks

    def _split_python(self, text: str) -> list[tuple[str | None, str, int, int]]:
        """Разбивает Python-код по top-level определениям (class, def, async def)."""
        # Паттерн: строка без отступа, начинается с class/def/async def
        pattern = re.compile(r"^(?:class|(?:async\s+)?def)\s+(\w+)", re.MULTILINE)
        matches = list(pattern.finditer(text))

        if not matches:
            return self._split_paragraphs(text)

        chunks: list[tuple[str | None, str, int, int]] = []

        # Преамбула (импорты, docstring модуля)
        if matches[0].start() > 0:
            preamble = text[: matches[0].start()]
            if preamble.strip():
                chunks.append(("imports", preamble, 0, matches[0].start()))

        # Каждое определение + его тело до следующего определения
        for i, match in enumerate(matches):
            definition_name = match.group(1)
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end]
            if content.strip():
                chunks.append((definition_name, content, start, end))

        return chunks

    def _split_paragraphs(self, text: str) -> list[tuple[str | None, str, int, int]]:
        """Fallback: разбивает по двойным переносам строк."""
        chunks: list[tuple[str | None, str, int, int]] = []
        # Разделяем по 2+ пустым строкам
        parts = re.split(r"\n\s*\n", text)
        pos = 0
        for part in parts:
            # Находим реальную позицию в оригинальном тексте
            actual_start = text.find(part, pos)
            if actual_start == -1:
                actual_start = pos
            actual_end = actual_start + len(part)
            if part.strip():
                chunks.append((None, part, actual_start, actual_end))
            pos = actual_end

        return chunks
