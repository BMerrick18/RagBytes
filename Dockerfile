FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install . && useradd --create-home app && mkdir data && chown app data

USER app
ARG VERSION=dev
ENV RAGBYTES_VERSION=$VERSION \
    WEB_CONCURRENCY=2
EXPOSE 8000
CMD ["uvicorn", "ragbytes.main:app", "--host", "0.0.0.0", "--port", "8000"]
