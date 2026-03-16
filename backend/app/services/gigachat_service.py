from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from app.config import settings


async def get_chat_response(messages: list[dict]) -> str:
    """Отправляет сообщения в GigaChat и возвращает ответ."""
    giga_messages = [
        Messages(role=MessagesRole(m["role"]), content=m["content"])
        for m in messages
    ]
    payload = Chat(messages=giga_messages, model=settings.gigachat_model)

    async with GigaChat(
        credentials=settings.gigachat_credentials,
        verify_ssl_certs=settings.gigachat_verify_ssl,
    ) as client:
        response = await client.achat(payload)

    return response.choices[0].message.content
