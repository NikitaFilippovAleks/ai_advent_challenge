"""Стратегия разбиения текста на чанки фиксированного размера с перекрытием."""

from app.modules.indexing.strategies.base import BaseChunkingStrategy, ChunkResult


class FixedSizeStrategy(BaseChunkingStrategy):
    """Скользящее окно фиксированного размера с перекрытием.

    Разбивает текст на чанки по chunk_size символов с шагом (chunk_size - overlap).
    Старается разрывать по ближайшей границе предложения.
    """

    def __init__(self, chunk_size: int = 500, overlap: int = 100) -> None:
        self._chunk_size = chunk_size
        self._overlap = overlap

    @property
    def name(self) -> str:
        return "fixed_size"

    def _find_break_point(self, text: str, target: int) -> int:
        """Ищет ближайшую границу предложения вблизи target позиции.

        Проверяет последние 20% окна на наличие разделителей (.!?\\n).
        Если не найдено — возвращает target как есть.
        """
        # Область поиска: последние 20% от chunk_size
        search_start = max(0, target - self._chunk_size // 5)
        search_area = text[search_start:target]

        # Ищем последний разделитель предложения в области
        for sep in ["\n\n", "\n", ". ", "! ", "? "]:
            pos = search_area.rfind(sep)
            if pos != -1:
                return search_start + pos + len(sep)

        return target

    def chunk(self, text: str, source: str) -> list[ChunkResult]:
        """Разбивает текст скользящим окном с перекрытием."""
        if not text.strip():
            return []

        chunks: list[ChunkResult] = []
        step = self._chunk_size - self._overlap
        pos = 0
        index = 0

        while pos < len(text):
            end = min(pos + self._chunk_size, len(text))

            # Если не конец текста — ищем хорошую точку разрыва
            if end < len(text):
                end = self._find_break_point(text, end)

            chunk_text = text[pos:end].strip()
            if chunk_text:
                chunks.append(ChunkResult(
                    content=chunk_text,
                    chunk_index=index,
                    section=None,
                    char_start=pos,
                    char_end=end,
                ))
                index += 1

            # Шаг вперёд (но не назад и не на месте)
            new_pos = pos + step
            if new_pos <= pos:
                new_pos = pos + 1
            pos = new_pos

            # Если мы уже захватили конец текста — выходим
            if end >= len(text):
                break

        return chunks
