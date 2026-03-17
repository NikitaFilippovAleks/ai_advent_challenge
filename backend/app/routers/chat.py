from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.gigachat_service import get_available_models, get_chat_response

router = APIRouter()


class MessageItem(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[MessageItem]
    style: str = "normal"
    model: str | None = None


class ChatResponse(BaseModel):
    content: str


@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        messages = [m.model_dump() for m in request.messages]
        content = await get_chat_response(messages, style=request.style, model=request.model)
        return ChatResponse(content=content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/models")
async def models():
    try:
        available = await get_available_models()
        return {"models": available}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
