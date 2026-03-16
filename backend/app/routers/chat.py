from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.gigachat_service import get_chat_response

router = APIRouter()


class MessageItem(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[MessageItem]


class ChatResponse(BaseModel):
    content: str


@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        messages = [m.model_dump() for m in request.messages]
        content = await get_chat_response(messages)
        return ChatResponse(content=content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
