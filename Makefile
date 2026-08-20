PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.PHONY: install init seed run test e2e review openapi migrate package docker-up docker-down
install:
	python -m pip install -r requirements.txt
init:
	python scripts/init_db.py
seed:
	python scripts/seed_demo.py
run:
	uvicorn apps.api.src.main:app --host 0.0.0.0 --port 8000 --reload
test:
	pytest -q
e2e:
	$(PYTHON) scripts/run_v12_e2e.py
review:
	python scripts/task_review.py --task manual-review --title "人工全量评审"
openapi:
	python scripts/export_openapi.py
migrate:
	alembic upgrade head
package:
	python scripts/package_release.py --version V1.0.0-P0
docker-up:
	docker compose up -d --build
docker-down:
	docker compose down
