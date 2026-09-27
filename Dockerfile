FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY scripts ./scripts
COPY samples ./samples

RUN mkdir -p uploads outputs models_cache

EXPOSE 8000

# The schema is managed by Alembic. Run `alembic upgrade head` before starting
# the API (docker-compose does this in the one-shot `migrate` service).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
