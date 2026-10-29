.PHONY: test lint run docker-build

test:
	cd backend && .venv/bin/python -m pytest -q

lint:
	cd backend && .venv/bin/ruff check app tests scripts && .venv/bin/ruff format --check app tests scripts

run:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

docker-build:
	docker build -t afefehub-backend backend

# --- infrastructure (infra/terraform, AWS_PROFILE=prod) ---
.PHONY: infra-init infra-plan infra-apply infra-output
TF := AWS_PROFILE=prod terraform -chdir=infra/terraform

infra-init:
	AWS_PROFILE=prod infra/terraform/bootstrap.sh && $(TF) init

infra-plan:
	$(TF) plan

infra-apply:
	$(TF) apply

infra-output:
	$(TF) output
