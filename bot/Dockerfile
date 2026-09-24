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

# Mode B (P4): run the always-on live monitor (reports at REPORT_HOURS + intraday alerts).
# One-shot report instead: `docker compose run --rm bot python -m src.main`
CMD ["python", "-m", "src.monitor.engine"]
