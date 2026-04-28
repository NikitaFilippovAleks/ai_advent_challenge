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

## AI Code Review

В репозитории настроен автоматический AI-ревью PR'ов через GitHub Actions.

**Как это работает:**

1. На любой `pull_request` (open/synchronize/reopened) запускается workflow [`.github/workflows/ai-code-review.yml`](.github/workflows/ai-code-review.yml).
2. Внутри собирается образ `backend` и запускается one-shot контейнер с CLI: `python -m app.modules.code_review.cli`.
3. CLI берёт `git diff base...head` + список изменённых файлов, индексирует проектную документацию (`.claude/CLAUDE.md`, `.claude/rules/*`, `README.md`) в RAG-индекс через GigaChat-эмбеддинги, ищет релевантные правила и одним вызовом GigaChat генерирует Markdown-ревью со структурой:
   - `## Потенциальные баги`
   - `## Архитектурные проблемы`
   - `## Рекомендации`
4. Результат постится комментарием в PR. При повторных пушах в ту же ветку комментарий **обновляется**, а не дублируется (используется HTML-маркер `<!-- ai-code-review -->`).

**Настройка:**

- В Settings → Secrets and variables → Actions добавить secret `GIGACHAT_CREDENTIALS`.
- Workflow автоматически скипается на PR из форков (GitHub не пробрасывает secrets форкам).

**Локальный запуск:**

```bash
docker compose run --rm backend python -m app.modules.code_review.cli \
  --base origin/master --head HEAD --output /repo/.review-output.md
cat .review-output.md
```

**Замечание про конфиденциальность:** diff отправляется в GigaChat API. Для репозиториев с чувствительным кодом — оценить риски перед включением.
