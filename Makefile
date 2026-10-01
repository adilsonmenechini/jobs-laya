install:
	uv sync --extra dev
	uv run patchright install chromium
	uv run pre-commit install

test:
	uv run pytest -q

eval:
	uv run python eval/evaluate.py

lint:
	uv run ruff check --fix .
	uv run ruff format .

hooks:
	uv run pre-commit install

run:
	uv run uvicorn app.main:app --reload --port 3080

login:
	uv run python -m app.linkedin.login
