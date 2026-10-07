ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}
RUN pip install --no-cache-dir uv==0.12.23
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/app ./app
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
RUN useradd --uid 10001 --create-home app && mkdir -p /data/documents /data/fetcher && chown -R app:app /data
USER app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
