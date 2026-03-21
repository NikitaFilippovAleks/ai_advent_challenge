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
    temperature: float | None = None


class UsageInfo(BaseModel):
    """Информация об использовании токенов."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):
    content: str
    usage: UsageInfo | None = None


@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        messages = [m.model_dump() for m in request.messages]
        result = await get_chat_response(messages, style=request.style, model=request.model, temperature=request.temperature)
        return ChatResponse(
            content=result["content"],
            usage=result.get("usage"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/models")
async def models():
    try:
        available = await get_available_models()
        return {"models": available}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
