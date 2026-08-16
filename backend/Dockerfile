# Bay Area AI Events Finder — backend (FastAPI + LLM pipeline)
#
# This image is unusual: the Luma connector spawns `npx @playwright/mcp` (Node)
# from Python and drives a real Chromium. So the image needs FOUR things baked in:
#   1. Python   — the FastAPI app + Groq pipeline
#   2. Node.js  — to run `npx @playwright/mcp`
#   3. Chromium — the browser Playwright automates
#   4. Chromium's OS libraries — installed via `playwright install --with-deps`
#
# Build (from the backend/ directory):
#   docker build -t events-finder-backend .
# Run locally:
#   docker run -p 8081:8081 --env-file .env events-finder-backend
#
# On Cloud Run, $PORT is injected automatically (defaults to 8081 here).

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    NODE_MAJOR=20 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# --- System layer: Node.js 20 (for @playwright/mcp) + minimal tooling ---
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Python deps (own layer so code changes don't bust the pip cache) ---
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# --- Playwright MCP server + Chromium + its OS libraries ---
# `--with-deps` apt-installs the exact shared libraries Chromium needs, so the
# scraper won't crash at runtime with a missing-.so error.
RUN npm install -g @playwright/mcp playwright \
    && playwright install --with-deps chromium

# --- Application code (last, so edits rebuild only this thin layer) ---
COPY app ./app

# --- Run as a non-root user ---
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app /ms-playwright
USER appuser

EXPOSE 8081

# Shell form so ${PORT} (set by Cloud Run) expands; falls back to 8081 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8081}"]



