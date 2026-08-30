FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml requirements.lock README.md ./
COPY src ./src
COPY apps ./apps
COPY alembic.ini ./
COPY migrations ./migrations
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
    && pip install --no-cache-dir --no-deps .
EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
