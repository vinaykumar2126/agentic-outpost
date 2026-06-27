# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Bay Area AI events aggregator — a personal tool that nightly pulls events from Luma (via mcp-playwright), scores them with Claude for relevance to AI engineering / agentic AI roles, and displays them in a filterable Next.js feed.

**Stack:** FastAPI (Python) backend + Next.js 15 (TypeScript) frontend + SQLite + Anthropic SDK + APScheduler + mcp-playwright.

**Phase 1 source:** Luma (lu.ma) via `@playwright/mcp` — browser automation extracts event data since Luma has no public API.

## Commands

### Backend
```bash
cd backend
cp .env.example .env          # fill in EVENTBRITE_API_KEY and ANTHROPIC_API_KEY
pip install -r requirements.txt
pip install -r requirements-dev.txt

make dev                      # uvicorn app.main:app --reload (port 8000)
make test                     # pytest tests/ -v
make test-one TEST=tests/test_connectors.py::test_pagination  # run a single test
make scrape                   # manually trigger nightly collection job
make rank                     # manually run Claude ranking on unscored events
```

### Frontend
```bash
cd frontend
npm install
npm run dev                   # Next.js dev server (port 3000)
npm run build && npm start    # production build
npm run lint
```

### Prerequisites
```bash
# Ollama (local inference — no API key needed)
ollama pull qwen2.5       # default model; override with OLLAMA_MODEL in .env
ollama serve              # if not already running as a background service

# MCP playwright (for Luma browser extraction)
npm install -g @playwright/mcp
npx playwright install chromium
```

### Manual API trigger (while backend is running)
```bash
curl -X POST http://localhost:8000/api/admin/scrape/trigger
curl http://localhost:8000/api/events?min_score=7&sort_by=score
curl http://localhost:8000/api/health
```

## Architecture

### Data flow
```
[APScheduler @ 2am PT]
  → EventConnector.fetch_events()   # pulls from Eventbrite API
  → upsert_events(db, events)       # dedup by (source, external_id)
  → ClaudeRanker.rank_unscored()    # batches of 20, tool-use structured output
  → FastAPI GET /api/events         # read-mostly REST API
  → Next.js page.tsx                # SSR + client-side filters
```

### Connector plugin pattern
Each event source is one file implementing `EventConnector` ABC from `backend/app/connectors/base.py`. Adding a new source = create one file + uncomment one line in `backend/app/connectors/registry.py`. The scheduler, ranker, API, and frontend require zero changes.

`is_available()` on each connector checks prerequisites (credentials, MCP server availability) — missing deps skip that connector gracefully at startup.

### MCP integration (Luma connector)
`backend/app/connectors/luma.py` uses the Python `mcp` SDK to spawn `@playwright/mcp --headless` as a subprocess via `StdioServerParameters`. The connector:
1. Calls `browser_navigate` to `https://lu.ma/discover?location=sf-bay-area&tag=ai`
2. Calls `browser_snapshot` to get the page accessibility tree
3. Scrolls and re-snapshots to load more events (Luma paginates via infinite scroll)
4. Parses event titles, dates, URLs, organizers from the snapshot text
5. For each event URL, navigates to the detail page and extracts description + location

`is_available()` checks that `npx @playwright/mcp --version` exits 0.

### AI ranking (local via Ollama)
`backend/app/ranking/event_ranker.py` uses the `ollama` Python SDK to call a locally running Ollama instance — no external API, no cost. Structured JSON output is enforced via Ollama's `format` schema parameter. Batch size 20. Events with `relevance_score IS NULL` are selected each run; events whose title/description changed since last rank get reset to NULL automatically during upsert.

Model and endpoint are configurable via env vars: `OLLAMA_MODEL` (default `llama3.1`) and `OLLAMA_BASE_URL` (default `http://localhost:11434`).

Scoring rubric (baked into system prompt):
- 9–10: Agentic AI workflows / multi-agent systems in production / AI engineering career events
- 7–8: LLM engineering, AI infrastructure, production deployment, agent frameworks
- 5–6: General AI/ML engineering content
- 0–4: Not relevant or only loosely AI-adjacent

### Scheduling
APScheduler `BackgroundScheduler` is embedded in the FastAPI process, started in the `lifespan` context manager (`backend/app/main.py`). Cron: `hour=2, minute=0, timezone="America/Los_Angeles"`. Use `POST /api/admin/scrape/trigger` during development to run immediately without waiting.

### Database
SQLite via SQLAlchemy ORM. Swap to Postgres by changing `DATABASE_URL` env var only — no code changes. Key dedup constraint: `UNIQUE(source, external_id)`. Key index: `(start_datetime, relevance_score)`.

### Frontend state
`FilterBar.tsx` is a client component that syncs filter state to URL search params (`useSearchParams` / `useRouter`). `page.tsx` is a server component that reads those params and passes them to the `getEvents()` fetch — enabling SSR on initial load with no client-side flash.

## Environment Variables

All in `backend/.env` (never committed). Required: `EVENTBRITE_API_KEY`, `ANTHROPIC_API_KEY`. Optional: `DATABASE_URL` (default `sqlite:///./events.db`), `SCRAPE_DAYS_AHEAD` (default `60`), `LOG_LEVEL` (default `INFO`).