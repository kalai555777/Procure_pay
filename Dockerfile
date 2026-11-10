FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# 1. Install the packages first, so this layer is reused when only code changes
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

# 2. Then the project itself
COPY README.md ./
COPY src ./src
COPY tests ./tests
RUN uv sync --locked

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["fastapi", "run", "src/procure_pay/main.py", "--port", "8000"]