# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Bay Area AI events aggregator — a personal tool that nightly pulls events from Luma (via mcp-playwright), scores them with Claude for relevance to AI engineering / agentic AI roles, and displays them in a filterable Next.js feed.

**Stack:** FastAPI (Python) backend + Next.js 15 (TypeScript) frontend + SQLite + Groq SDK + APScheduler + mcp-playwright.

**Phase 1 source:** Luma (lu.ma) via `@playwright/mcp` — browser automation extracts event data since Luma has no public API.

## Commands

### Backend
```bash
cd backend
cp .env.example .env          # fill in GROQ_API_KEY
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
# Groq (hosted inference — free tier). Get a key at https://console.groq.com/keys
# Set GROQ_API_KEY in backend/.env; override the model with GROQ_MODEL

# MCP playwright (for Luma browser extraction)
npm install -g @playwright/mcp
npx playwright install chromium
```

### Manual API trigger (while backend is running)
```bash
curl -X POST http://localhost:8000/api/admin/scrape/trigger
curl http://localhost:8000/api/events?min_score=7&sort_by=score
curl http://localhost:8000/api/admin/health
```

## Architecture

### Data flow
```
[APScheduler @ 2am PT]
  → EventConnector.fetch_events()   # pulls from Eventbrite API
  → upsert_events(db, events)       # dedup by (source, external_id)
  → EventRanker.rank_unscored()     # batches of 20, Groq JSON-mode structured output
  → FastAPI GET /api/events         # read-mostly REST API
  → Next.js page.tsx                # SSR + client-side filters
```

### Connector plugin pattern
Each event source is one file implementing `EventConnector` ABC from `backend/app/connectors/base.py`. Adding a new source = create one file + one line in `backend/app/connectors/registry.py`. The scheduler, ranker, API, and frontend require zero changes. Active sources: `luma`, `aicamp`, `reddit` (registry order matters — reddit runs last so its cross-source dedup sees what luma/aicamp just inserted).

`is_available()` on each connector checks prerequisites (credentials, MCP server availability) — missing deps skip that connector gracefully at startup.

### MCP integration (Luma connector)
`backend/app/connectors/luma.py` uses the Python `mcp` SDK to spawn `@playwright/mcp --headless` as a subprocess via `StdioServerParameters`. The connector:
1. Calls `browser_navigate` to `https://lu.ma/discover?location=sf-bay-area&tag=ai`
2. Calls `browser_snapshot` to get the page accessibility tree
3. Scrolls and re-snapshots to load more events (Luma paginates via infinite scroll)
4. Parses event titles, dates, URLs, organizers from the snapshot text
5. For each event URL, navigates to the detail page and extracts description + location

`is_available()` checks that `npx @playwright/mcp --version` exits 0.

### Reddit connector (public RSS feeds)
`backend/app/connectors/reddit.py` discovers community/word-of-mouth events via Reddit's public Atom feeds (`/r/<sub>/search.rss`, `hot.rss`, `<post>/.rss`) — no credentials needed. (Reddit's Data API now requires per-use-case approval under the Nov 2025 Responsible Builder Policy; RSS remains an intentionally public syndication surface and includes full post bodies + exact ISO timestamps.) Rate discipline: descriptive User-Agent, 10s between fetches (~10 req/min unauthenticated limit with burst accounting — repeated dev runs drain the same IP bucket), 429 backoff honoring Retry-After (61s/122s fallback), and an adaptive per-run slowdown after any exhausted 429. Megathread scan covers city subs only. The 2am cron doesn't care that the run takes a few minutes. Pipeline: narrow search feeds (6 subreddits × OR-combined queries, sort=new/t=week) + megathread comments → `trim_post()` code-level field projection → one recall-biased Groq JSON extraction pass → lu.ma out-links enriched via the existing Playwright scraper → cross-source dedup (resolved URL, fallback normalized title+date) → `RawEvent` with `source="reddit"`. Raw feed XML is audited to `.agent/scratch/reddit_raw/`, never held in LLM context.

### AI ranking (hosted via Groq)
`backend/app/ranking/event_ranker.py` uses the `groq` Python SDK to call Groq's OpenAI-compatible chat completions API (free tier). Structured JSON output is enforced via `response_format={"type": "json_object"}`; the model returns `{"rankings": [...]}`. Batch size 20. Events with `relevance_score IS NULL` are selected each run; events whose title/description changed since last rank get reset to NULL automatically during upsert.

Model is configurable via `GROQ_MODEL` (default `llama-3.3-70b-versatile`); the key comes from `GROQ_API_KEY`.

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

All in `backend/.env` (never committed). Required: `GROQ_API_KEY`. Optional: `GROQ_MODEL` (default `llama-3.3-70b-versatile`), `DATABASE_URL` (default `sqlite:///./events.db`), `SCRAPE_DAYS_AHEAD` (default `60`), `LOG_LEVEL` (default `INFO`).
