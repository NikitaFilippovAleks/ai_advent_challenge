"""Ollama-провайдер — реализация BaseLLMProvider для удалённого Ollama-сервера.

Используется в playground как альтернатива локальному LM Studio.
Авторизация — HTTP Basic, эндпоинты: /api/chat (диалог + стриминг NDJSON),
/api/tags (список загруженных моделей).

Function calling и эмбеддинги намеренно не реализованы — для playground
они не нужны, как и в LMStudioProvider.
"""

import json
import logging
from collections.abc import AsyncGenerator

import httpx

from app.core.config import settings
from app.shared.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    """Провайдер для удалённого Ollama через REST API с Basic Auth."""

    def _auth(self) -> httpx.BasicAuth | None:
        """Basic auth, если в конфиге задан логин/пароль; иначе без авторизации."""
        if settings.ollama_username and settings.ollama_password:
            return httpx.BasicAuth(settings.ollama_username, settings.ollama_password)
        return None

    def _client(self, timeout: float = 300.0) -> httpx.AsyncClient:
        """Создаёт httpx-клиент, нацеленный на ollama_base_url с авторизацией."""
        return httpx.AsyncClient(
            base_url=settings.ollama_base_url.rstrip("/"),
            auth=self._auth(),
            timeout=timeout,
        )

    @staticmethod
    def _options(temperature: float | None, max_tokens: int | None) -> dict:
        """Собирает блок options для Ollama, выкидывая None-значения."""
        options: dict = {}
        if temperature is not None:
            options["temperature"] = temperature
        # num_predict — лимит токенов в ответе. Дефолт 2048 как в LMStudio.
        options["num_predict"] = max_tokens if max_tokens is not None else 2048
        return options

    @staticmethod
    def _usage_from(payload: dict) -> dict | None:
        """Конвертирует prompt_eval_count/eval_count в формат usage."""
        prompt_tokens = payload.get("prompt_eval_count")
        completion_tokens = payload.get("eval_count")
        if prompt_tokens is None and completion_tokens is None:
            return None
        prompt_tokens = prompt_tokens or 0
        completion_tokens = completion_tokens or 0
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
        functions: list | None = None,
        max_tokens: int | None = None,
    ) -> dict:
        """Нестримовый запрос к /api/chat. functions игнорируется."""
        body = {
            "model": model or settings.ollama_default_model,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "stream": False,
            "options": self._options(temperature, max_tokens),
        }
        async with self._client() as client:
            resp = await client.post("/api/chat", json=body)
            resp.raise_for_status()
            data = resp.json()

        return {
            "content": (data.get("message") or {}).get("content", ""),
            "usage": self._usage_from(data),
        }

    async def stream(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[dict, None]:
        """NDJSON-стриминг от /api/chat. Формат событий — как в LMStudio."""
        body = {
            "model": model or settings.ollama_default_model,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "stream": True,
            "options": self._options(temperature, max_tokens),
        }
        async with self._client() as client:
            async with client.stream("POST", "/api/chat", json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        # Пропускаем битые строки — Ollama изредка может слать пустые keepalive
                        logger.warning("Ollama: невалидная NDJSON-строка: %r", line)
                        continue

                    msg = chunk.get("message") or {}
                    content = msg.get("content")
                    if content:
                        yield {
                            "type": "delta",
                            "data": {"content": content, "type": "content"},
                        }

                    if chunk.get("done"):
                        usage = self._usage_from(chunk)
                        if usage:
                            yield {"type": "usage", "data": usage}
                        yield {"type": "done", "data": {}}
                        return

    async def list_models(self) -> list[dict]:
        """Возвращает список моделей, загруженных в Ollama (/api/tags)."""
        async with self._client(timeout=30.0) as client:
            resp = await client.get("/api/tags")
            resp.raise_for_status()
            data = resp.json()

        models = data.get("models", []) or []
        return [{"id": m["name"], "name": m["name"]} for m in models if "name" in m]
