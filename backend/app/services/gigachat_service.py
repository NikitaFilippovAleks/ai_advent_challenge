from gigachat import (
    GigaChat,
)
from gigachat.models import (
    Chat,
    Messages,
    MessagesRole,
)

from app.config import (
    settings,
)


async def get_available_models() -> list[dict]:
    """Возвращает список доступных моделей GigaChat."""
    async with GigaChat(
        credentials=settings.gigachat_credentials,
        verify_ssl_certs=settings.gigachat_verify_ssl,
    ) as client:
        response = await client.aget_models()

    return [{"id": m.id_, "name": m.id_} for m in response.data]


async def get_chat_response(
    messages: list[dict], style: str = "normal", model: str | None = None, temperature: float | None = None
) -> str:
    """Отправляет сообщения в GigaChat и возвращает ответ."""
    giga_messages = []

    # Для кастомного стиля добавляем системный промпт
    if style == "custom":
        giga_messages.append(
            Messages(
                role=MessagesRole.SYSTEM,
                content=(
                    "Отвечай как маленькая девочка, которая вставляет в ответ весёлые словечки. "
                    "Ответ должен быть не длиннее 200 символов. "
                ),
            )
        )

    giga_messages.extend(
        Messages(role=MessagesRole(m["role"]), content=m["content"]) for m in messages
    )

    max_tokens = 200 if style == "custom" else 1024
    payload = Chat(
        messages=giga_messages,
        model=model or settings.gigachat_model,
        max_tokens=max_tokens,
        temperature=temperature,
        additional_fields={"stop": ["огурец"]} if style == "custom" else None,
    )

    async with GigaChat(
        credentials=settings.gigachat_credentials,
        verify_ssl_certs=settings.gigachat_verify_ssl,
    ) as client:
        response = await client.achat(payload)

    # Извлекаем информацию об использовании токенов
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
