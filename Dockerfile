FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv sync --extra dev --no-install-project
RUN uv run --no-sync patchright install --with-deps chromium

COPY . .

EXPOSE 3080

CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3080"]
