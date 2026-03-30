"""GigaChat провайдер — реализация BaseLLMProvider для GigaChat SDK от Сбера."""

from collections.abc import AsyncGenerator

from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

from app.core.config import settings
from app.shared.llm.base import BaseLLMProvider


class GigaChatProvider(BaseLLMProvider):
    """Провайдер для работы с GigaChat API."""

    def _create_client(self) -> GigaChat:
        """Создаёт клиент GigaChat с настройками из конфига."""
        return GigaChat(
            credentials=settings.gigachat_credentials,
            verify_ssl_certs=settings.gigachat_verify_ssl,
        )

    def _build_messages(self, messages: list[dict]) -> list[Messages]:
        """Преобразует список словарей в объекты Messages для SDK."""
        return [
            Messages(role=MessagesRole(m["role"]), content=m["content"])
            for m in messages
        ]

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
    ) -> dict:
        """Отправляет сообщения в GigaChat и возвращает полный ответ."""
        payload = Chat(
            messages=self._build_messages(messages),
            model=model or settings.gigachat_model,
            max_tokens=1024,
            temperature=temperature,
        )

        async with self._create_client() as client:
            response = await client.achat(payload)

        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return {
            "content": response.choices[0].message.content,
            "usage": usage,
        }

    async def stream(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Стримит ответ от GigaChat чанками через async-генератор.

        Генерирует события:
        - {"type": "delta", "data": {"content": "...", "type": "content"}}
        - {"type": "usage", "data": {"prompt_tokens": ..., ...}}
        - {"type": "done", "data": {}}
        """
        payload = Chat(
            messages=self._build_messages(messages),
            model=model or settings.gigachat_model,
            max_tokens=1024,
            temperature=temperature,
            update_interval=0.1,
        )

        async with self._create_client() as client:
            async for chunk in client.astream(payload):
                choice = chunk.choices[0]

                # Отправляем текстовый чанк
                if choice.delta.content:
                    yield {
                        "type": "delta",
                        "data": {"content": choice.delta.content, "type": "content"},
                    }

                # В последнем чанке приходят usage и finish_reason
                if choice.finish_reason:
                    if chunk.usage:
                        yield {
                            "type": "usage",
                            "data": {
                                "prompt_tokens": chunk.usage.prompt_tokens,
                                "completion_tokens": chunk.usage.completion_tokens,
                                "total_tokens": chunk.usage.total_tokens,
                            },
                        }
                    yield {"type": "done", "data": {}}

    async def list_models(self) -> list[dict]:
        """Возвращает список доступных моделей GigaChat."""
        async with self._create_client() as client:
            response = await client.aget_models()
        return [{"id": m.id_, "name": m.id_} for m in response.data]

    async def generate_title(self, user_message: str, assistant_response: str) -> str:
        """Генерирует короткое название диалога по первому обмену сообщениями."""
        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "Придумай короткое название (3-5 слов) для диалога. "
                    "Отвечай ТОЛЬКО названием, без кавычек и пояснений."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Пользователь: {user_message}\n"
                    f"Ассистент: {assistant_response[:200]}"
                ),
            },
        ]
        result = await self.chat(prompt_messages, temperature=0.3)
        return result["content"].strip()[:100]
