# Стек технологий

## Бэкенд
- **Python 3.12** — язык
- **FastAPI** — веб-фреймворк (async, автодокументация через Swagger)
- **uvicorn[standard]** — ASGI-сервер с hot-reload
- **gigachat** — SDK для работы с GigaChat LLM от Сбера
- **pydantic-settings** — загрузка конфигурации из .env
- **SQLAlchemy 2.0 async** — ORM с async/await поддержкой
- **aiosqlite** — async-драйвер для SQLite

## Фронтенд
- **React 19** — UI-фреймворк
- **TypeScript 5.6** — типизация
- **Vite 6** — сборщик и dev-сервер с HMR и proxy

## Инфраструктура
- **Docker** — контейнеризация (python:3.12-slim, node:24-slim)
- **Docker Compose** — оркестрация backend + frontend
- **VSCode Dev Containers** — конфигурация для разработки в контейнере

## Зависимости
- Backend: `backend/requirements.txt`
- Frontend: `frontend/package.json`
