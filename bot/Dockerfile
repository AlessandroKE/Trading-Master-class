FROM python:3.12-slim

# Faster, cleaner Python in containers
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY config ./config
COPY src ./src

# SQLite DB dir (mounted as a volume in compose)
RUN mkdir -p /app/data

# Run as non-root
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

# P1: run one scan and exit. (P3+ will switch to a long-running scheduler/loop.)
CMD ["python", "-m", "src.main"]
