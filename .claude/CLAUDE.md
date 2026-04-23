# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Описание проекта

GigaChat — веб-приложение для чата с LLM (GigaChat от Сбера). Монорепо с FastAPI бэкендом и React фронтендом, работающими в Docker-контейнерах.

## ВАЖНО: Выполнение команд

**Все команды (сборка, линтинг, тесты, npm/pip и т.д.) выполняются ТОЛЬКО внутри Docker-контейнеров** через `docker compose exec`. Не запускай команды напрямую на хост-машине.

```bash
# Бэкенд
docker compose exec backend <команда>

# Фронтенд
docker compose exec frontend <команда>
```

## Команды

### Запуск (из корня проекта)
```bash
make dev          # docker compose up — запуск контейнеров
make build        # docker compose up --build — пересборка и запуск
make down         # docker compose down — остановка
make shell-backend   # bash в контейнер бэкенда
make shell-frontend  # bash в контейнер фронтенда
```

### Внутри контейнеров
```bash
make run-backend    # uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
make run-frontend   # npx vite --host 0.0.0.0
```

### Frontend (из frontend/)
```bash
npm run dev       # dev server (port 5173)
npm run build     # TypeScript + Vite production сборка
```

## Архитектура

**Бэкенд (Python 3.12, FastAPI) — доменно-модульная архитектура:**

Три слоя: `core/` (инфраструктура) → `shared/` (общие абстракции) → `modules/` (бизнес-домены).
Правило импортов: каждый слой импортирует только из слоёв ниже. Модули не импортируют друг друга (кроме `dependencies.py` для DI).

- `backend/app/main.py` — Composition Root: создаёт FastAPI, подключает роутеры модулей
- `backend/app/models.py` — ORM-модели: Conversation, Message, Summary, ConversationFact, Branch, ShortTermInsight, LongTermMemory, UserProfile, Invariant, Task, IndexedDocument, DocumentChunk
- `backend/app/core/config.py` — pydantic-settings, загружает переменные из `.env`
- `backend/app/core/database.py` — SQLAlchemy async engine, session factory, init_db, миграции
- `backend/app/core/exceptions.py` — базовые исключения (NotFoundError, ValidationError)
- `backend/app/shared/llm/base.py` — BaseLLMProvider ABC (абстракция над LLM-провайдером)
- `backend/app/shared/llm/gigachat.py` — GigaChatProvider (реализация для GigaChat SDK)
- `backend/app/modules/chat/` — обработка сообщений (router, service, schemas, dependencies)
- `backend/app/modules/conversations/` — CRUD диалогов (router, repository, schemas)
- `backend/app/modules/context/` — стратегии контекста, факты, ветки (router, service, repository, schemas, strategies/)
- `backend/app/modules/memory/` — трёхуровневая память ассистента (router, service, repository, schemas, dependencies)
- `backend/app/modules/agent/` — агентная архитектура с MCP-интеграцией: MCPManager управляет подключениями к MCP-серверам (stdio), AgentRunner реализует agent loop (LLM → function_call → tool → повтор), GigaChat адаптер конвертирует MCP ↔ GigaChat форматы; REST API для управления серверами (router, mcp_manager, mcp_config, gigachat_adapter, schemas, runner, tools, types, dependencies)
- `backend/mcp_servers/git_server.py` — MCP-сервер для Git (4 инструмента: git_status, git_log, git_diff, git_branches), запускается как subprocess через stdio
- `backend/app/modules/profiles/` — CRUD профилей пользователя (system prompt для LLM), привязка к диалогам; profiles_router регистрируется первым в main.py (чтобы /default не конфликтовал с /{id})
- `backend/app/modules/invariants/` — глобальные инварианты (правила, которые ассистент обязан соблюдать): CRUD, toggle, инъекция в system prompt LLM
- `backend/app/modules/tasks/` — конечный автомат задач (FSM): классификация сообщений, фазы planning→execution→validation→done, пауза/отмена (state_machine, service, repository, router, schemas)
- `backend/app/modules/scheduler/` — планировщик задач с периодическим выполнением: APScheduler, сбор данных через MCPManager, генерация сводок через AgentRunner (service, repository, router, schemas, dependencies)
- `backend/app/modules/indexing/` — индексация документов с эмбеддингами: 2 стратегии chunking (fixed_size, structural), генерация эмбеддингов через GigaChat SDK, семантический поиск по cosine similarity, реранкинг (threshold/keyword/LLM cross-encoder), query rewriting, сравнение стратегий и режимов реранкинга (router, service, repository, schemas, dependencies, strategies/). Модуль `rag_context.py` — общая функция построения RAG-системного промпта с двухэтапным поиском (эмбеддер по обогащённому запросу + keyword-rerank по оригинальному), используется и основным чатом, и playground.
- `backend/app/modules/playground/` — stateless-чат с локальной моделью через LM Studio (OpenAI-совместимый API). Без БД, памяти, агента и стратегий контекста; поддерживает опциональный RAG (использует `rag_context.build_rag_context` и общий `IndexingService`). SSE-события: `delta`, `usage`, `done`, `error`, `sources`. Параметр `max_tokens` пробрасывается в `LMStudioProvider` (дефолт 2048), используется сравнительным режимом для оптимизации под узкий кейс.
- `backend/mcp_servers/scheduler_server.py` — MCP-сервер планировщика (5 инструментов: create_scheduled_task, list_scheduled_tasks, get_task_results, get_task_summary, cancel_scheduled_task), отдельная БД scheduler.db
- `backend/mcp_servers/research_server.py` — MCP-сервер для исследования файлов (3 инструмента: search_files, summarize_text, save_to_file), демонстрирует композицию инструментов в пайплайн
- `backend/mcp_servers/system_server.py` — MCP-сервер системной информации (4 инструмента: current_datetime, disk_usage, list_processes, env_info)
- `backend/mcp_servers/notes_server.py` — MCP-сервер заметок (5 инструментов: create_note, get_note, list_notes, search_notes, delete_note), хранение в /app/data/notes.json

**Фронтенд (React 19, TypeScript, Vite):**
- `frontend/src/App.tsx` — корневой компонент, один ChatWindow на весь экран
- `frontend/src/components/ChatWindow.tsx` — стейт сообщений, стриминг-отправка, переключатель стратегий контекста
- `frontend/src/components/FactsPanel.tsx` — панель ключевых фактов (стратегия sticky_facts)
- `frontend/src/components/BranchPanel.tsx` — панель веток диалога (стратегия branching)
- `frontend/src/components/MemoryPanel.tsx` — панель трёхуровневой памяти (стратегия memory)
- `frontend/src/components/ProfilesModal.tsx` — модальное окно управления профилями (CRUD + выбор дефолтного)
- `frontend/src/components/InvariantsModal.tsx` — модальное окно управления инвариантами (CRUD + toggle вкл/выкл)
- `frontend/src/components/TaskPanel.tsx` — панель статуса задачи: фаза, прогресс, пауза/отмена
- `frontend/src/components/MCPPanel.tsx` — панель управления MCP-серверами: подключение/отключение, список инструментов
- `frontend/src/components/SchedulerPanel.tsx` — панель планировщика: задачи, результаты сбора, сводки, управление (пауза/удаление)
- `frontend/src/components/SourcesPanel.tsx` — отображение RAG-источников под ответом ассистента (файл, секция, score)
- `frontend/src/api/scheduler.ts` — API-клиент: задачи, результаты, сводки, пауза/возобновление/удаление
- `frontend/src/api/tasks.ts` — API-клиент: активная задача, переходы фаз, история
- `frontend/src/api/mcp.ts` — API-клиент: CRUD MCP-серверов, connect/disconnect, список инструментов
- `frontend/src/components/ProfileSelector.tsx` — выпадающий список выбора профиля для конкретного диалога
- `frontend/src/api/chat.ts` — API-клиент: чат, стриминг, стратегии, факты, ветки
- `frontend/src/api/profiles.ts` — API-клиент: CRUD профилей, привязка профиля к диалогу
- `frontend/src/api/invariants.ts` — API-клиент: CRUD инвариантов, toggle
- `frontend/src/components/PlaygroundWindow.tsx` — stateless-раздел для LM Studio: выбор локальной модели, temperature, system prompt, опциональный RAG с реранкингом и панелью источников. Поддерживает два режима: `single` (один чат) и `compare` (два подчата бок-о-бок — Baseline vs Optimized — для оценки эффекта оптимизации параметров и prompt-шаблона).
- `frontend/src/components/PlaygroundCompareView.tsx` — режим сравнения: две колонки с независимыми стейтами и общим инпутом, параллельный стриминг в обе стороны.
- `frontend/src/components/playgroundCompareConfig.ts` — захардкоженные конфигурации Baseline (t=0.7, max=2048, без system prompt) и Optimized (t=0.1, max=150, few-shot JSON-классификатор тикетов поддержки).
- `frontend/src/api/playground.ts` — API-клиент LM Studio: список моделей, SSE-стриминг, события `sources`, параметр `max_tokens`.
- `frontend/src/types/index.ts` — интерфейсы Message, ChatRequest, ContextStrategy, Fact, Branch, UserProfile и др.

**Взаимодействие:** Фронтенд → Vite proxy (`/api` → `http://backend:8000`) → FastAPI → GigaChat SDK

**Стриминг:** `POST /api/chat/stream` → SSE-события (delta, tool_call, tool_result, usage, done, error) → `fetch` + `ReadableStream`

**RAG:** Флаг `use_rag: true` в ChatRequest активирует поиск по индексированным документам. Параметры `rag_rerank_mode` (none/threshold/keyword/llm_cross_encoder) и `rag_score_threshold` управляют постобработкой результатов. Найденные чанки вставляются в system prompt, SSE-событие `sources` (с original_score и rerank_score) отправляется перед генерацией текста. Поддерживается query rewriting через LLM и сравнение режимов реранкинга.

**MCP-серверы:** Конфигурация в `backend/data/mcp_servers.json`. При старте приложения MCPManager автоматически подключает серверы с `enabled: true`. Агент использует инструменты через GigaChat function calling. Зарегистрированные серверы: git (4 инструмента), scheduler (5), research (3), system (4), notes (5) — итого 21 инструмент.

**Порты:** Backend 8000, Frontend 5173

## API контракт

```
POST /api/chat
Body: { messages: [{ role, content }], model?, temperature?, use_rag?, rag_rerank_mode?, rag_score_threshold? }
Response: { content: string, usage?: { prompt_tokens, completion_tokens, total_tokens } }

POST /api/chat/stream (SSE)
Body: { messages: [{ role, content }], model?, temperature?, use_rag? }
Events: sources → { sources: [...] }, delta → { content, type }, usage → { prompt_tokens, ... }, done → {}, error → { message }

GET /api/models
Response: { models: [{ id, name }] }

GET /api/conversations/{id}/strategy
Response: { strategy: "summary" | "sliding_window" | "sticky_facts" | "branching" | "memory" }

PUT /api/conversations/{id}/strategy
Body: { strategy: string }

GET /api/conversations/{id}/facts
Response: { facts: [{ key, value, updated_at }] }

PUT /api/conversations/{id}/facts
Body: { key, value }

DELETE /api/conversations/{id}/facts/{key}

GET /api/conversations/{id}/branches
Response: { branches: [{ id, name, checkpoint_message_id, created_at }], active_branch_id }

POST /api/conversations/{id}/branches
Body: { name, checkpoint_message_id }

PUT /api/conversations/{id}/branches/{branch_id}/activate

GET /api/memory/{id}
Response: { short_term: [...], working: [...], long_term: [...] }

GET/POST/DELETE /api/memory/{id}/short-term[/{insight_id}]
GET/PUT/DELETE /api/memory/{id}/working[/{key}]
GET/PUT/DELETE /api/memory/long-term[/{memory_id}]
GET /api/memory/long-term/search?q=...

GET /api/profiles
Response: { profiles: [{ id, name, system_prompt, is_default, created_at, updated_at }] }

POST /api/profiles
Body: { name, system_prompt, is_default? }

GET /api/profiles/default
Response: { id, name, system_prompt, is_default, ... } | null

GET /api/profiles/{id}
PUT /api/profiles/{id}
Body: { name?, system_prompt?, is_default? }
DELETE /api/profiles/{id}

GET /api/conversations/{id}/profile
Response: { profile: ProfileOut | null, source: "explicit" | "default" | "none" }

PUT /api/conversations/{id}/profile
Body: { profile_id: string | null }

GET /api/invariants
Response: [{ id, name, description, category, is_active, priority, created_at, updated_at }]

POST /api/invariants
Body: { name, description, category?, is_active?, priority? }

GET /api/invariants/{id}
PUT /api/invariants/{id}
Body: { name?, description?, category?, is_active?, priority? }

DELETE /api/invariants/{id}

PATCH /api/invariants/{id}/toggle
Response: InvariantOut (переключает is_active)

GET /api/tasks/{conversation_id}/active
Response: TaskOut | null

PUT /api/tasks/{task_id}/transition
Body: { phase: string }
Response: TaskOut | 400

PUT /api/tasks/{task_id}/plan
Body: { steps: [{ description: string }] }
Response: TaskOut

GET /api/tasks/{conversation_id}/history
Response: TaskOut[]

GET /api/mcp/servers
Response: [{ name, command, args, enabled, connected, tool_count }]

POST /api/mcp/servers
Body: { name, command, args? }
Response: MCPServerStatus

DELETE /api/mcp/servers/{name}

POST /api/mcp/servers/{name}/connect
Response: { status: "connected", tools: int }

POST /api/mcp/servers/{name}/disconnect
Response: { status: "disconnected" }

GET /api/mcp/tools
Response: [{ server, name, description }]

GET /api/scheduler/tasks
Response: [{ id, name, tool_name, tool_args, cron_expression, summary_cron, status, results_count, created_at }]

GET /api/scheduler/tasks/{id}/results?limit=10
Response: [{ collected_at, data }]

GET /api/scheduler/tasks/{id}/summary
Response: { summary, period_start, period_end, created_at } | null

POST /api/scheduler/tasks/{id}/summarize
Response: { summary, period_start, period_end, created_at }

PUT /api/scheduler/tasks/{id}/pause
Response: { status: "paused" }

PUT /api/scheduler/tasks/{id}/resume
Response: { status: "active" }

DELETE /api/scheduler/tasks/{id}
Response: { status: "deleted" }

POST /api/indexing/index
Body: { paths: [string], strategy?: "fixed_size" | "structural" }
Response: [{ document_id, filename, chunk_count, strategy }]

POST /api/indexing/search
Body: { query: string, top_k?: int, rerank_mode?: "none"|"threshold"|"keyword"|"llm_cross_encoder", score_threshold?: float, top_k_initial?: int, top_k_final?: int, rewrite_query?: bool }
Response: { query, results: [{ chunk_id, document_id, source, section, content, score, original_score?, rerank_score? }], rewritten_query?, rerank_mode, filtered_count }

GET /api/indexing/documents
Response: [{ id, filename, title, chunking_strategy, chunk_count, created_at }]

GET /api/indexing/documents/{doc_id}
Response: { id, filename, title, chunking_strategy, chunk_count, created_at }

DELETE /api/indexing/documents/{doc_id}
Response: { status: "deleted", document_id }

POST /api/indexing/rerank-compare
Body: { query: string, top_k_initial?: int, top_k_final?: int, score_threshold?: float, rewrite_query?: bool }
Response: { query, rewritten_query?, modes: { "none": SearchResponse, "threshold": SearchResponse, "keyword": SearchResponse } }

POST /api/indexing/compare
Body: { paths: [string], query: string, top_k?: int }
Response: { query, strategies: [{ strategy, chunk_count, avg_chunk_length, results: [...] }] }

GET /api/playground/models
Response: { models: [{ id, name }] }

POST /api/playground/chat
Body: { messages: [{ role, content }], model?, temperature?, max_tokens?, system_prompt?, use_rag?, rag_rerank_mode?, rag_score_threshold?, rag_top_k? }
Response: { content, usage?, sources?, low_relevance? }

POST /api/playground/chat/stream (SSE)
Body: { messages, model?, temperature?, max_tokens?, system_prompt?, use_rag?, rag_rerank_mode?, rag_score_threshold?, rag_top_k? }
Events: sources → { sources: [...], low_relevance: bool } (при use_rag), delta → { content }, usage → {...}, done → {}, error → { message }
```

## Стратегии управления контекстом

- **summary** (по умолчанию) — суммаризация старых сообщений через GigaChat, последние N остаются как есть
- **sliding_window** — только последние N сообщений, остальное отбрасывается
- **sticky_facts** — KV-память (факты) + последние N сообщений; факты извлекаются автоматически после каждого ответа
- **branching** — чекпоинты и ветки диалога; можно создать несколько веток от одного места и переключаться между ними
- **memory** — трёхуровневая память: краткосрочная (наблюдения текущего диалога) + рабочая (данные задачи) + долгосрочная (кросс-диалоговые знания); LLM автоматически распределяет информацию по уровням

## Инварианты

Глобальные правила, которые ассистент обязан соблюдать в каждом ответе. Хранятся в таблице `invariants`, не привязаны к конкретному диалогу.

Категории: `architecture`, `technical`, `stack`, `business`.

Активные инварианты инжектируются как system-сообщение с наивысшим приоритетом (позиция 0 в массиве messages), перед system prompt профиля. LLM получает инструкцию отказать при конфликте запроса с инвариантом и объяснить причину.

## Стек

- **Backend:** Python 3.12, FastAPI, uvicorn, gigachat SDK, pydantic-settings, SQLAlchemy 2.0 async + aiosqlite, APScheduler 3.x, croniter, numpy
- **Frontend:** React 19, TypeScript 5.6, Vite 6
- **Infra:** Docker, Docker Compose

## Стиль кода

- **Python:** async/await, Pydantic-модели для валидации, комментарии на русском
- **TypeScript:** strict mode, функциональные компоненты с хуками, интерфейсы для типов
- **Общее:** без классовых компонентов React, роутеры — тонкие (бизнес-логика в сервисах), компоненты не делают прямых HTTP-запросов
- **DI:** FastAPI `Depends()` + `lru_cache` для синглтонов, кросс-модульный импорт только в `dependencies.py`

## Актуализация документации

При внесении изменений в проект Claude должен обновлять соответствующую документацию:
- **CLAUDE.md** — при изменении архитектуры, добавлении/удалении эндпоинтов, смене стека, новых командах сборки/запуска
- **`.claude/rules/`** — при изменении стиля кода, архитектурных паттернов или стека технологий
- **README.md** — при изменении инструкций по установке, запуску или описания проекта

Если добавляется новый сервис, роутер, компонент или зависимость, которые меняют общую картину проекта — обнови соответствующие секции. Не нужно обновлять документацию при мелких правках, которые не влияют на архитектуру или процесс разработки.

## Переменные окружения

Хранятся в `.env` (не коммитится), пример в `.env.example`:
- `GIGACHAT_CREDENTIALS` — токен авторизации GigaChat
- `GIGACHAT_VERIFY_SSL` — проверка SSL (по умолчанию false)
- `GIGACHAT_MODEL` — модель (по умолчанию GigaChat)
