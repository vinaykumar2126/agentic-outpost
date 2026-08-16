# Bay Area AI Events Finder

A personal aggregator that nightly pulls AI/ML events across the Bay Area, scores each one with an LLM for relevance to **AI engineering / agentic AI** roles, and serves them in a filterable, relevance-ranked feed.

## Live URLs

| Service   | URL                                                             | Host       |
| --------- | --------------------------------------------------------------- | ---------- |
| Frontend  | https://frontend-self-tau-37.vercel.app                         | Vercel     |
| Backend   | https://events-backend-806237478519.us-central1.run.app         | Cloud Run  |
| API docs  | https://events-backend-806237478519.us-central1.run.app/docs    | Cloud Run  |
| Health    | https://events-backend-806237478519.us-central1.run.app/api/admin/health | Cloud Run |

> The frontend reads the backend URL from the `NEXT_PUBLIC_API_BASE_URL` env var (set in Vercel). Locally it defaults to `http://localhost:8000`.

## Stack

- **Backend:** FastAPI (Python) · SQLAlchemy · SQLite (dev) / Cloud SQL (prod) · APScheduler · Groq SDK · mcp-playwright
- **Frontend:** Next.js 16 (App Router, TypeScript) · React 19 · Tailwind CSS v4
- **Deploy:** Backend → Google Cloud Run · Frontend → Vercel · Scraping runs **locally** (Mac LaunchAgent) and writes to the cloud DB

## Architecture at a glance

```
                        ┌─────────────────────────────────────────┐
                        │  Nightly job (APScheduler @ 2am PT)      │
                        │  runs LOCALLY on the Mac                 │
                        └───────────────────┬─────────────────────┘
                                            │
      ┌──────────────┬──────────────┬───────┴───────┐
      ▼              ▼              ▼               ▼
  Luma connector  AICamp        Reddit         (add a file to
  (Playwright     connector     connector       register more)
   MCP)                          (public RSS)
      └──────────────┴──────────────┴───────────────┘
                     │  RawEvent[]  (dedup by source+external_id)
                     ▼
             upsert_events()  ──►  Database (SQLite / Cloud SQL)
                     │
                     ▼
             EventRanker.rank_unscored()   # Groq JSON-mode, batches of 20
                     │  relevance_score 0–10
                     ▼
        FastAPI  GET /api/events  ──►  Next.js feed (SSR + URL-synced filters)
```

### Data flow

1. **Collect** — each source's `EventConnector.fetch_events()` returns `RawEvent`s.
2. **Store** — `upsert_events()` dedups by `UNIQUE(source, external_id)`. Events whose title/description changed since last rank have `relevance_score` reset to `NULL`.
3. **Rank** — `EventRanker.rank_unscored()` sends unscored events (batches of 20) to Groq with JSON-mode structured output; scores 0–10.
4. **Serve** — FastAPI exposes a read-mostly REST API.
5. **Display** — Next.js server component fetches events (SSR) and renders a relevance-sorted, filterable list.

## Repository layout

```
events_finder/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app + lifespan (starts APScheduler), CORS
│   │   ├── config.py          # env-driven settings
│   │   ├── database.py        # SQLAlchemy engine/session
│   │   ├── models.py          # Event, ScrapeRun ORM models
│   │   ├── schemas.py         # Pydantic request/response models
│   │   ├── llm.py             # Groq client wiring
│   │   ├── api/
│   │   │   ├── events.py      # GET /api/events, GET /api/events/{id}
│   │   │   └── admin.py       # POST /api/admin/scrape/trigger, /scrape/runs, /health
│   │   ├── connectors/        # one file per source (plugin pattern)
│   │   │   ├── base.py        # EventConnector ABC
│   │   │   ├── registry.py    # active sources (order matters)
│   │   │   ├── luma.py        # lu.ma via @playwright/mcp
│   │   │   ├── aicamp.py      # AICamp
│   │   │   └── reddit.py      # public Reddit RSS/Atom feeds
│   │   ├── ranking/
│   │   │   └── event_ranker.py  # Groq JSON-mode scoring
│   │   ├── scheduler/jobs.py  # nightly collect + rank job
│   │   └── notifications/email.py
│   ├── evals/                 # LangSmith evaluations
│   ├── tests/
│   ├── Dockerfile             # Cloud Run image
│   ├── Makefile               # dev / test / scrape / rank targets
│   └── requirements*.txt
├── frontend/
│   ├── app/
│   │   ├── page.tsx           # server component: SSR feed + filters
│   │   ├── events/[id]/page.tsx  # event detail page
│   │   └── layout.tsx
│   ├── components/            # EventCard, FilterBar, ScoreBar
│   ├── lib/api.ts             # typed fetch client (reads NEXT_PUBLIC_API_BASE_URL)
│   └── types/event.ts         # shared TS types
├── CLAUDE.md                  # working notes for AI assistants
├── FLOW.md                    # detailed pipeline walkthrough
└── SOURCES.md                 # per-source scraping notes
```

## API reference

Base: `https://events-backend-806237478519.us-central1.run.app`

| Method | Path                          | Description                                             |
| ------ | ----------------------------- | ------------------------------------------------------- |
| GET    | `/api/events`                 | List events. Filters: `min_score`, `sort_by` (`score`\|`date`), `q`, `is_free`, `is_online`, `date_from`, `date_to`, `limit`, `offset` |
| GET    | `/api/events/{id}`            | Single event detail                                     |
| POST   | `/api/admin/scrape/trigger`   | Run collection + ranking immediately                    |
| GET    | `/api/admin/scrape/runs`      | Recent scrape-run history                               |
| GET    | `/api/admin/health`           | Health / connector-availability check                  |

Example:

```bash
curl "https://events-backend-806237478519.us-central1.run.app/api/events?min_score=7&sort_by=score"
```

## Event sources

| Source   | Mechanism                              | Notes |
| -------- | -------------------------------------- | ----- |
| `luma`   | `@playwright/mcp` browser automation   | Luma has no public API; the connector navigates + snapshots the accessibility tree |
| `aicamp` | Direct scrape                          | — |
| `reddit` | Public Atom/RSS feeds (no credentials) | Runs last so cross-source dedup sees luma/aicamp inserts |

**Adding a source:** create one file implementing `EventConnector` in `backend/app/connectors/` and add one line to `registry.py`. The scheduler, ranker, API, and frontend need zero changes.

## Ranking rubric

Scored 0–10 by Groq (default model `llama-3.3-70b-versatile`):

- **9–10** — Agentic AI workflows / multi-agent systems in production / AI engineering career events
- **7–8** — LLM engineering, AI infrastructure, production deployment, agent frameworks
- **5–6** — General AI/ML engineering content
- **0–4** — Not relevant or only loosely AI-adjacent

## Local development

### Backend

```bash
cd backend
cp .env.example .env          # fill in GROQ_API_KEY
pip install -r requirements.txt
pip install -r requirements-dev.txt

make dev                      # uvicorn app.main:app --reload (port 8000)
make test                     # pytest tests/ -v
make scrape                   # trigger collection manually
make rank                     # rank unscored events manually
```

### Frontend

```bash
cd frontend
npm install
npm run dev                   # http://localhost:3000
npm run build && npm start    # production build
```

### Prerequisites

```bash
# Groq API key (free tier): https://console.groq.com/keys → GROQ_API_KEY in backend/.env
npm install -g @playwright/mcp    # for the Luma connector
npx playwright install chromium
```

## Environment variables

**Backend** (`backend/.env`, never committed):

| Var                | Required | Default                      | Purpose                     |
| ------------------ | -------- | ---------------------------- | --------------------------- |
| `GROQ_API_KEY`     | ✅       | —                            | Groq inference key          |
| `GROQ_MODEL`       |          | `llama-3.3-70b-versatile`    | Ranking model               |
| `DATABASE_URL`     |          | `sqlite:///./events.db`      | Swap to Postgres/Cloud SQL  |
| `SCRAPE_DAYS_AHEAD`|          | `60`                         | Look-ahead window           |
| `LOG_LEVEL`        |          | `INFO`                       | Logging verbosity           |

**Frontend** (Vercel project env / `.env.local`):

| Var                        | Value                                                     |
| -------------------------- | --------------------------------------------------------- |
| `NEXT_PUBLIC_API_BASE_URL` | `https://events-backend-806237478519.us-central1.run.app` |

## Deployment

- **Backend → Cloud Run:** built from `backend/Dockerfile`; connects to Cloud SQL via `DATABASE_URL`.
- **Frontend → Vercel:** root directory `frontend/`, Next.js auto-detected, `NEXT_PUBLIC_API_BASE_URL` set as a production env var. Redeploy with `npx vercel --prod` from `frontend/` (or connect the Git repo for auto-deploys on push).
- **Scraping:** the nightly APScheduler job runs **locally** (Mac LaunchAgent) and writes into the cloud database — the Cloud Run service is read/serve-only for events.
