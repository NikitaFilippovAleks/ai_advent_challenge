# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Описание проекта

GigaChat — веб-приложение для чата с LLM (GigaChat от Сбера). Монорепо с FastAPI бэкендом и React фронтендом, работающими в Docker-контейнерах.

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

**Бэкенд (Python 3.12, FastAPI):**
- `backend/app/main.py` — точка входа FastAPI, подключает роутеры
- `backend/app/routers/chat.py` — эндпоинты `POST /api/chat` и `POST /api/chat/stream` (SSE)
- `backend/app/routers/context.py` — эндпоинты управления стратегиями контекста, фактами и ветками
- `backend/app/services/gigachat_service.py` — интеграция с GigaChat SDK (обычный и стриминг-ответ)
- `backend/app/services/context_service.py` — 4 стратегии управления контекстом (summary, sliding_window, sticky_facts, branching)
- `backend/app/services/agent/` — каркас агентной архитектуры (types, tools, runner)
- `backend/app/models.py` — ORM-модели: Conversation, Message, Summary, ConversationFact, Branch
- `backend/app/config.py` — pydantic-settings, загружает переменные из `.env`

**Фронтенд (React 19, TypeScript, Vite):**
- `frontend/src/App.tsx` — корневой компонент, один ChatWindow на весь экран
- `frontend/src/components/ChatWindow.tsx` — стейт сообщений, стриминг-отправка, переключатель стратегий контекста
- `frontend/src/components/FactsPanel.tsx` — панель ключевых фактов (стратегия sticky_facts)
- `frontend/src/components/BranchPanel.tsx` — панель веток диалога (стратегия branching)
- `frontend/src/api/chat.ts` — API-клиент: чат, стриминг, стратегии, факты, ветки
- `frontend/src/types/index.ts` — интерфейсы Message, ChatRequest, ContextStrategy, Fact, Branch и др.

**Взаимодействие:** Фронтенд → Vite proxy (`/api` → `http://backend:8000`) → FastAPI → GigaChat SDK

**Стриминг:** `POST /api/chat/stream` → SSE-события (delta, usage, done, error) → `fetch` + `ReadableStream`

**Порты:** Backend 8000, Frontend 5173

## API контракт

```
POST /api/chat
Body: { messages: [{ role, content }], model?, temperature? }
Response: { content: string, usage?: { prompt_tokens, completion_tokens, total_tokens } }

POST /api/chat/stream (SSE)
Body: { messages: [{ role, content }], model?, temperature? }
Events: delta → { content, type }, usage → { prompt_tokens, ... }, done → {}, error → { message }

GET /api/models
Response: { models: [{ id, name }] }

GET /api/conversations/{id}/strategy
Response: { strategy: "summary" | "sliding_window" | "sticky_facts" | "branching" }

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
```

## Стратегии управления контекстом

- **summary** (по умолчанию) — суммаризация старых сообщений через GigaChat, последние N остаются как есть
- **sliding_window** — только последние N сообщений, остальное отбрасывается
- **sticky_facts** — KV-память (факты) + последние N сообщений; факты извлекаются автоматически после каждого ответа
- **branching** — чекпоинты и ветки диалога; можно создать несколько веток от одного места и переключаться между ними

## Стек

- **Backend:** Python 3.12, FastAPI, uvicorn, gigachat SDK, pydantic-settings
- **Frontend:** React 19, TypeScript 5.6, Vite 6
- **Infra:** Docker, Docker Compose

## Стиль кода

- **Python:** async/await, Pydantic-модели для валидации, комментарии на русском
- **TypeScript:** strict mode, функциональные компоненты с хуками, интерфейсы для типов
- **Общее:** без классовых компонентов React, разделение на роуты/сервисы/компоненты

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
