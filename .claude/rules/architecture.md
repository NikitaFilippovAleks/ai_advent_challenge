# Архитектура

## Общая структура
Монорепо с двумя сервисами: `backend/` (FastAPI) и `frontend/` (React + Vite), оркестрированными через Docker Compose.

## Бэкенд — слоистая архитектура
- **Routers** (`app/routers/`) — определение HTTP-эндпоинтов, валидация входных данных через Pydantic-модели
- **Services** (`app/services/`) — бизнес-логика и интеграция с внешними API (GigaChat SDK)
- **Config** (`app/config.py`) — единая точка конфигурации через pydantic-settings

Новые эндпоинты добавляются как роутеры и подключаются в `main.py`. Вся работа с LLM — через сервисный слой.

## Фронтенд — компонентная архитектура
- **Components** (`src/components/`) — React-компоненты с хуками
- **API** (`src/api/`) — модуль для HTTP-запросов к бэкенду
- **Types** (`src/types/`) — общие TypeScript-интерфейсы

Vite dev server проксирует `/api` на бэкенд — фронтенд не знает реальный адрес бэкенда.

## Сетевое взаимодействие
```
Browser → Vite proxy (/api) → FastAPI (port 8000) → GigaChat API
```
