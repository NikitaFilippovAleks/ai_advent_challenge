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
- `backend/app/routers/chat.py` — единственный эндпоинт `POST /api/chat`
- `backend/app/services/gigachat_service.py` — асинхронная интеграция с GigaChat SDK
- `backend/app/config.py` — pydantic-settings, загружает переменные из `.env`

**Фронтенд (React 19, TypeScript, Vite):**
- `frontend/src/App.tsx` — корневой компонент, рендерит ChatWindow
- `frontend/src/components/ChatWindow.tsx` — главный компонент: стейт сообщений, отправка, автоскролл
- `frontend/src/api/chat.ts` — API-клиент, отправляет POST /api/chat
- `frontend/src/types/index.ts` — интерфейсы Message, ChatRequest, ChatResponse

**Взаимодействие:** Фронтенд → Vite proxy (`/api` → `http://backend:8000`) → FastAPI → GigaChat SDK

**Порты:** Backend 8000, Frontend 5173

## API контракт

```
POST /api/chat
Body: { messages: [{ role: "user"|"assistant", content: string }] }
Response: { content: string }
```

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
