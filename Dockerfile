# syntax=docker/dockerfile:1.7
#
# Confidential Agent Market — FastAPI app for Phala Cloud TDX deployment.
# Target arch: linux/amd64 (Intel TDX requires x86_64).

# ── Builder: install Python deps with the compiler toolchain ───────────────
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libssl-dev \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-prod.txt ./
RUN pip install --prefix=/install -r requirements-prod.txt


# ── Runtime: slim image with installed packages + app source ───────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy resolved packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app
COPY api      ./api
COPY agents   ./agents
COPY contracts ./contracts

# Non-root user
RUN groupadd --system app \
    && useradd  --system --gid app --no-create-home app \
    && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
