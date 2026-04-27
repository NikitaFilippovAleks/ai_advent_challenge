"""Composition Root — точка сборки приложения.

Единственное место, которое знает про все модули.
Все остальные файлы импортируют только из своего слоя.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

# Настройка логирования — INFO для модулей приложения
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logging.getLogger("app").setLevel(logging.INFO)
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import init_db
from app.modules.agent.dependencies import get_agent_runner, get_mcp_manager
from app.modules.agent.router import router as agent_router
from app.modules.chat.router import router as chat_router
from app.modules.context.router import router as context_router
from app.modules.conversations.router import router as conversations_router
from app.modules.invariants.router import router as invariants_router
from app.modules.memory.router import router as memory_router
from app.modules.profiles.router import router as profiles_router
from app.modules.scheduler.dependencies import get_scheduler_service
from app.modules.scheduler.router import router as scheduler_router
from app.modules.indexing.dependencies import get_indexing_service
from app.modules.indexing.project_docs_indexer import index_project_docs
from app.modules.indexing.router import router as indexing_router
from app.modules.playground.router import router as playground_router
from app.modules.tasks.router import router as tasks_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация БД и подключение MCP-серверов при старте."""
    await init_db()
    # Подключаем MCP-серверы с enabled=true
    mcp = get_mcp_manager()
    await mcp.auto_connect()
    # Автоиндексация README + docs/ для команды /help.
    # Отдельной задачей в фоне не уносим: индексер сам проверяет lock-сигнатуру
    # и при отсутствии изменений завершается мгновенно.
    try:
        await index_project_docs(get_indexing_service())
    except Exception as e:
        logger.error("Автоиндексация project_docs упала: %s", e, exc_info=True)
    # Запускаем планировщик задач
    scheduler_svc = get_scheduler_service()
    await scheduler_svc.start(mcp, get_agent_runner())
    yield
    # Останавливаем планировщик
    scheduler_svc = get_scheduler_service()
    await scheduler_svc.stop()
    # Отключаем все MCP-серверы при остановке
    await mcp.shutdown()


app = FastAPI(title="GigaChat API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profiles_router)
app.include_router(invariants_router)
app.include_router(chat_router)
app.include_router(context_router)
app.include_router(conversations_router)
app.include_router(memory_router)
app.include_router(tasks_router)
app.include_router(agent_router)
app.include_router(scheduler_router)
app.include_router(indexing_router)
app.include_router(playground_router)
