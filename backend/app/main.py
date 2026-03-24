from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.chat import router as chat_router
from app.routers.conversations import router as conversations_router
from app.services.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация БД при старте приложения."""
    await init_db()
    yield


app = FastAPI(title="GigaChat API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(conversations_router)
