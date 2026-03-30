"""Composition Root — точка сборки приложения.

Единственное место, которое знает про все модули.
Все остальные файлы импортируют только из своего слоя.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import init_db
from app.modules.chat.router import router as chat_router
from app.modules.context.router import router as context_router
from app.modules.conversations.router import router as conversations_router


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
app.include_router(context_router)
app.include_router(conversations_router)
