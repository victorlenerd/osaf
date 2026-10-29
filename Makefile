.PHONY: test lint run docker-build

test:
	cd backend && .venv/bin/python -m pytest -q

lint:
	cd backend && .venv/bin/ruff check app tests scripts && .venv/bin/ruff format --check app tests scripts

run:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

docker-build:
	docker build -t afefehub-backend backend
