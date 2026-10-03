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

# Skills locais de agente (.claude/skills/). NAME é kebab-case minúsculo.
# O comando nunca sobrescreve skill existente e nunca escreve fora de .claude/skills/.
skill:
	@python3 scripts/make_skill.py --dir "$(CURDIR)/.claude/skills" --name "$(NAME)"

skill-list:
	@python3 scripts/make_skill.py --dir "$(CURDIR)/.claude/skills" --list
