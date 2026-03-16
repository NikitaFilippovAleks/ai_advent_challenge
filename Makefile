# Запуск Docker Compose
dev:
	docker compose up

build:
	docker compose up --build

down:
	docker compose down

# Зайти в контейнер бэкенда
shell-backend:
	docker compose exec backend bash

# Зайти в контейнер фронтенда
shell-frontend:
	docker compose exec frontend bash

# Запуск серверов внутри контейнеров
# (выполнять после `docker compose exec` в соответствующем контейнере)

# Бэкенд: uvicorn с hot-reload
run-backend:
	docker compose exec backend uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Фронтенд: vite dev server
run-frontend:
	docker compose exec frontend npx vite --host 0.0.0.0
