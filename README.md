# GigaChat — чат-приложение

Минимальное чат-приложение с GigaChat LLM. FastAPI бэкенд + React фронтенд в Docker Compose.

## Быстрый старт

1. Скопировать `.env.example` в `.env` и заполнить `GIGACHAT_CREDENTIALS`
2. Запустить:
   ```bash
   docker compose up --build
   ```
3. Открыть http://localhost:5173

## Структура

- `backend/` — FastAPI + gigachat SDK, порт 8000
- `frontend/` — React + Vite + TypeScript, порт 5173
- Фронтенд проксирует `/api` на бэкенд через Vite

## Переменные окружения

| Переменная | Описание |
|---|---|
| `GIGACHAT_CREDENTIALS` | Авторизационные данные GigaChat |
| `GIGACHAT_VERIFY_SSL` | Проверка SSL (default: `false`) |
| `GIGACHAT_MODEL` | Модель (default: `GigaChat`) |
