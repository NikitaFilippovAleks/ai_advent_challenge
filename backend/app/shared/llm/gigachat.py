"""GigaChat провайдер — реализация BaseLLMProvider для GigaChat SDK от Сбера."""

from collections.abc import AsyncGenerator

import json as json_module

from gigachat import GigaChat
from gigachat.models import Chat, FunctionCall, Messages, MessagesRole

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
        """Преобразует список словарей в объекты Messages для SDK.

        Поддерживает role='function' с полем name (для результатов вызова функций).
        """
        result = []
        for m in messages:
            kwargs = {"role": MessagesRole(m["role"]), "content": m["content"]}
            # Для function-сообщений передаём имя функции
            if m.get("name"):
                kwargs["name"] = m["name"]
            # Для assistant-сообщений с вызовом функции передаём function_call
            if m.get("function_call"):
                fc = m["function_call"]
                args = fc["arguments"]
                # arguments должен быть dict
                if isinstance(args, str):
                    args = json_module.loads(args)
                kwargs["function_call"] = FunctionCall(name=fc["name"], arguments=args)
            result.append(Messages(**kwargs))
        return result

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
        functions: list | None = None,
    ) -> dict:
        """Отправляет сообщения в GigaChat и возвращает полный ответ.

        При передаче functions — LLM может вернуть function_call вместо текста.
        """
        payload_kwargs = {
            "messages": self._build_messages(messages),
            "model": model or settings.gigachat_model,
            "max_tokens": 2048,
            "temperature": temperature,
        }
        if functions:
            payload_kwargs["functions"] = functions
            payload_kwargs["function_call"] = "auto"

        payload = Chat(**payload_kwargs)

        async with self._create_client() as client:
            response = await client.achat(payload)

        message = response.choices[0].message

        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        result = {
            "content": message.content or "",
            "usage": usage,
        }

        # Если LLM решил вызвать функцию
        if message.function_call:
            args = message.function_call.arguments
            # arguments может быть строкой JSON или dict
            if isinstance(args, str):
                args = json_module.loads(args)
            result["function_call"] = {
                "name": message.function_call.name,
                "arguments": args,
            }

        return result

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
