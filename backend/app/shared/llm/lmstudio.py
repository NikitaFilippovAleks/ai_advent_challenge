"""LM Studio провайдер — реализация BaseLLMProvider для локального OpenAI-совместимого сервера.

LM Studio поднимает HTTP-сервер с OpenAI Chat Completions API.
Используется для тестирования маленьких локальных моделей (например llama-3.2-1b-instruct).
Function calling и эмбеддинги намеренно не реализованы — для playground-режима они не нужны.
"""

from collections.abc import AsyncGenerator

from openai import AsyncOpenAI

from app.core.config import settings
from app.shared.llm.base import BaseLLMProvider


class LMStudioProvider(BaseLLMProvider):
    """Провайдер для локального LM Studio через OpenAI-совместимый API."""

    def _create_client(self) -> AsyncOpenAI:
        """Создаёт асинхронный OpenAI-клиент, указывающий на локальный LM Studio."""
        return AsyncOpenAI(
            base_url=settings.lmstudio_base_url,
            api_key=settings.lmstudio_api_key,
        )

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
        functions: list | None = None,
    ) -> dict:
        """Отправляет сообщения и возвращает полный ответ.

        functions игнорируется — playground без агентных возможностей.
        """
        client = self._create_client()
        response = await client.chat.completions.create(
            model=model or settings.lmstudio_default_model,
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
            temperature=temperature,
            max_tokens=2048,
        )

        message = response.choices[0].message
        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return {
            "content": message.content or "",
            "usage": usage,
        }

    async def stream(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Стримит ответ чанками в едином формате BaseLLMProvider."""
        client = self._create_client()
        stream = await client.chat.completions.create(
            model=model or settings.lmstudio_default_model,
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
            temperature=temperature,
            max_tokens=2048,
            stream=True,
            stream_options={"include_usage": True},
        )

        async for chunk in stream:
            # Чанк usage приходит в последнем событии и может не иметь choices
            if chunk.usage:
                yield {
                    "type": "usage",
                    "data": {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens": chunk.usage.total_tokens,
                    },
                }

            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            if delta and delta.content:
                yield {
                    "type": "delta",
                    "data": {"content": delta.content, "type": "content"},
                }

            if choice.finish_reason:
                yield {"type": "done", "data": {}}

    async def list_models(self) -> list[dict]:
        """Возвращает список моделей, загруженных в LM Studio."""
        client = self._create_client()
        response = await client.models.list()
        return [{"id": m.id, "name": m.id} for m in response.data]
