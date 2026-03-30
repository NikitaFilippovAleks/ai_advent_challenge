# Архитектура

## Общая структура
Монорепо с двумя сервисами: `backend/` (FastAPI) и `frontend/` (React + Vite), оркестрированными через Docker Compose.

## Бэкенд — доменно-модульная архитектура

Три слоя с однонаправленными зависимостями:

```
core/           → только внешние библиотеки (+ app.models)
shared/         → core/ + внешние библиотеки
modules/X/      → core/ + shared/ + app.models
                  modules/X/ НЕ импортирует modules/Y/
                  (кроме dependencies.py для DI-сборки)
main.py         → всё (Composition Root)
```

### core/ — инфраструктура
- `config.py` — pydantic-settings, загрузка из `.env`
- `database.py` — SQLAlchemy async engine, session factory, `init_db()`, миграции
- `exceptions.py` — базовые исключения (`NotFoundError`, `ValidationError`)

Трогается редко. Не знает про бизнес-домены.

### shared/ — общие абстракции
- `llm/base.py` — `BaseLLMProvider(ABC)` с методами `chat()`, `stream()`, `list_models()`
- `llm/gigachat.py` — `GigaChatProvider` (реализация для GigaChat SDK)

Если нужен новый LLM-провайдер — добавить реализацию `BaseLLMProvider` сюда.

### modules/ — бизнес-домены

Каждый модуль содержит:
- `router.py` — тонкий HTTP-роутер (без бизнес-логики)
- `service.py` — бизнес-логика (опционально)
- `repository.py` — доступ к БД через SQLAlchemy
- `schemas.py` — Pydantic-модели запросов/ответов
- `dependencies.py` — FastAPI `Depends`-провайдеры (единственное место для кросс-модульного импорта)

**Модули:**
- `conversations/` — CRUD диалогов и сообщений
- `chat/` — обработка чат-сообщений, стриминг, оркестрация (ChatService)
- `context/` — стратегии контекста, факты, ветки + `strategies/` (4 стратегии)
- `agent/` — каркас ИИ-агента (runner, tools, types)

### models.py — ORM-модели (общий для всех модулей)
Conversation, Message, Summary, ConversationFact, Branch — используются репозиториями из разных модулей.

### main.py — Composition Root
Единственное место, которое знает про все модули. Создаёт FastAPI, подключает роутеры, настраивает middleware, запускает `init_db()` через lifespan.

## Фронтенд — компонентная архитектура
- **Components** (`src/components/`) — React-компоненты с хуками
- **API** (`src/api/`) — модуль для HTTP-запросов к бэкенду
- **Types** (`src/types/`) — общие TypeScript-интерфейсы

Vite dev server проксирует `/api` на бэкенд — фронтенд не знает реальный адрес бэкенда.

## Сетевое взаимодействие
```
Browser → Vite proxy (/api) → FastAPI (port 8000) → GigaChat API
```

## Добавление нового модуля

1. Создать папку `app/modules/<name>/` с `__init__.py`, `router.py`, `schemas.py`
2. При необходимости добавить `service.py`, `repository.py`, `dependencies.py`
3. Подключить роутер в `app/main.py`: `app.include_router(router)`
4. Импорты — только из `core/`, `shared/`, `app.models`
