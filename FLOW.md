# Application Flow

This document walks through every execution path in the app — startup, nightly data collection, ranking, API serving, and the frontend. Read this first when re-entering the codebase.

---

## 1. Startup (`make dev`)

```
uvicorn app.main:app --reload
        │
        └─► lifespan() context manager  [backend/app/main.py]
                │
                ├─► create_tables()     [backend/app/database.py]
                │       Imports all ORM models → runs CREATE TABLE IF NOT EXISTS
                │       Database: backend/events.db (SQLite)
                │
                ├─► create_scheduler()  [backend/app/scheduler/jobs.py]
                │       APScheduler BackgroundScheduler
                │       Cron job: nightly_scrape_job() at 2:00 AM PT every day
                │
                └─► scheduler.start()
                        Runs in background thread — FastAPI keeps serving requests
```

The app is now live at `http://localhost:8000`.

---

## 2. Nightly Data Collection (2am PT or manual trigger)

This is the core pipeline. It runs automatically every night, or you can trigger it manually:

```bash
curl -X POST http://localhost:8000/api/admin/scrape/trigger
# or
make scrape && make rank
```

### Full pipeline:

```
nightly_scrape_job()           [backend/app/scheduler/jobs.py]
        │
        ├─► get_active_connectors()    [backend/app/connectors/registry.py]
        │       Loops CONNECTOR_REGISTRY, calls is_available() on each
        │       Skips connectors whose dependencies are missing (no crash)
        │       Currently active: LumaConnector
        │
        └─► For each connector:
                │
                ├─► ScrapeRun created in DB  (status = "running")
                │
                ├─► connector.fetch_events()  ← async, bridged via asyncio.run()
                │
                ├─► upsert_events()
                │
                └─► EventRanker.rank_unscored()
```

---

## 3. Luma Scraping (inside `fetch_events`)

Luma has no public API, so we use MCP Playwright to control a real browser.

```
LumaConnector.fetch_events()   [backend/app/connectors/luma.py]
        │
        ├─► Spawns: npx @playwright/mcp --headless
        │       MCP server exposes browser tools over stdio
        │       Python mcp SDK: ClientSession wraps the stdio channel
        │
        ├─► _collect_event_urls()
        │       browser_navigate → https://lu.ma/sf
        │       wait 3s  (Next.js SPA needs time to render)
        │       Loop 4 times:
        │           browser_snapshot → get YAML accessibility tree
        │           _parse_event_urls() → regex finds "- /url: /slug" entries
        │           browser_evaluate  → window.scrollBy(0, 900)  (infinite scroll)
        │           wait 2s
        │       Returns: list of https://lu.ma/<slug> URLs
        │
        └─► For each event URL:
                _scrape_event_detail()
                    │
                    ├─► browser_navigate → event page
                    │
                    ├─► browser_evaluate → read window.__NEXT_DATA__
                    │       If present: _parse_from_next_data()
                    │           Structured JSON — title, dates, location, hosts, tags
                    │           Returns RawEvent immediately ✓
                    │
                    └─► Fallback: browser_snapshot → accessibility tree text
                            _parse_from_snapshot()
                                title  ← "Page Title: X · Luma" or h1
                                date   ← _parse_date_from_snapshot()
                                            finds "Thursday, June 25" pattern
                                            then searches for "5:00 PM" AFTER
                                            that position (avoids navbar clock)
                                location  ← "San Francisco" pattern
                                organizer ← text after "Hosted By"
                                desc      ← paragraph elements under "About Event"
                            Returns RawEvent
```

Each successfully scraped page → one `RawEvent` object (defined in `backend/app/connectors/base.py`).

<!-- 
   browser_navigate - Opens a URL in the headless Chromium tab.
   browser_snapshot - Returns the accessibility tree of the current page as text (not HTML — it's a structured outline of what's visible).
   browser_evaluate - Runs arbitrary JavaScript in the page and returns the result.
   browser_scroll_down - (old version) Scrolls the page down(But we're not using it here)
    -->

---

## 4. Upsert into Database

```
upsert_events(db, raw_events, scrape_run)   [backend/app/scheduler/jobs.py]
        │
        For each RawEvent:
        │
        ├─► Query: SELECT * FROM events WHERE source=? AND external_id=?
        │
        ├─► Not found → INSERT new Event row
        │       relevance_score = NULL  (will be ranked next step)
        │
        └─► Found → UPDATE existing row
                Check: did title or description change?
                    YES → reset relevance_score = NULL  (old score is stale)
                    NO  → keep existing score (no re-ranking needed)

        db.commit()
```

The `UNIQUE(source, external_id)` constraint is the dedup key — the same event can be scraped 100 times without creating duplicate rows.

---

## 5. AI Relevance Ranking (Ollama)

```
EventRanker.rank_unscored(db)   [backend/app/ranking/event_ranker.py]
        │
        ├─► SELECT * FROM events WHERE relevance_score IS NULL
        │
        └─► Process in batches of 20:
                _rank_batch(batch)
                    │
                    ├─► Build JSON payload: [{external_id, title, description, organizer, tags}]
                    │
                    ├─► ollama.Client.chat()
                    │       model: qwen2.5  (configured in .env)
                    │       system prompt: scoring rubric (0–10 scale)
                    │       format: RANKING_SCHEMA  ← forces valid JSON output
                    │
                    └─► Parse response → [{external_id, score, justification}]

                For each result:
                    validate 0.0 ≤ score ≤ 10.0
                    event.relevance_score = score
                    event.relevance_justification = justification
                    event.ranked_at = now

                db.commit()  ← per batch, so a failure in one batch doesn't block others
```

**Scoring rubric baked into system prompt:**
- 9–10: Agentic AI in production, multi-agent systems, AI engineering career events
- 7–8: LLM engineering, agent frameworks (LangChain, AutoGen, CrewAI), AI infra
- 5–6: General AI/ML engineering
- 0–4: Not relevant

---

## 6. REST API (FastAPI)

Once events are in the DB, the frontend and any API client can read them.

```
GET /api/events
        │
        ├─► Query params: min_score, max_score, date_from, date_to,
        │                 source, is_free, is_online, q, sort_by, limit, offset
        │
        ├─► Default date_from = today  (only upcoming events shown)
        │
        ├─► sort_by=score  → ORDER BY relevance_score DESC NULLS LAST, start_datetime ASC
        │   sort_by=date   → ORDER BY start_datetime ASC
        │
        └─► Returns: { events: [...], total, limit, offset }

GET /api/events/{id}         → full event detail including description

POST /api/admin/scrape/trigger  → runs nightly_scrape_job() immediately (dev shortcut)
GET  /api/admin/scrape/runs     → last 20 scrape audit records
GET  /api/admin/health          → scheduler status + next run time
```

---

## 7. Frontend (Next.js 15)

```
Browser hits http://localhost:3000
        │
        └─► page.tsx  [frontend/app/page.tsx]  ← Server Component (SSR)
                │
                ├─► Reads URL search params (min_score, sort_by, q, is_free, etc.)
                │
                ├─► getEvents(filters)  [frontend/lib/api.ts]
                │       fetch("http://localhost:8000/api/events?...")
                │       Returns typed EventListResponse
                │
                └─► Renders:
                        <FilterBar />   ← Client Component
                        <EventCard />   ← one per event (score badge, date, link)

FilterBar.tsx  [frontend/components/FilterBar.tsx]  ← "use client"
        │
        Every filter change:
        │
        └─► router.push("/?min_score=7&sort_by=score&...")
                │
                └─► URL update → Next.js re-runs page.tsx on server
                        → fresh fetch to backend with new params
                        → new HTML streamed to browser
                        No client-side state. Filters survive page refresh.
```

---

## Key Files at a Glance

| What you want to change | File |
|---|---|
| Add a new event source | `backend/app/connectors/<name>.py` + one line in `registry.py` |
| Change the scoring rubric | `backend/app/ranking/event_ranker.py` → `SYSTEM_PROMPT` |
| Change scrape schedule | `backend/app/scheduler/jobs.py` → `create_scheduler()` |
| Add an API filter | `backend/app/api/events.py` → `list_events()` |
| Change what the card shows | `frontend/components/EventCard.tsx` |
| Add a filter to the UI | `frontend/components/FilterBar.tsx` |
| Swap SQLite → Postgres | `DATABASE_URL=postgresql://...` in `backend/.env` — no code changes |
| Change Ollama model | `OLLAMA_MODEL=<model>` in `backend/.env` |

---

## Environment at a Glance

```
backend/.env          ← secrets and config (never committed)
backend/events.db     ← SQLite database (never committed)
backend/.env.example  ← template showing all available variables
```

Required env vars: none (everything has defaults). Optional overrides:
- `OLLAMA_MODEL` (default: `qwen2.5`)
- `OLLAMA_BASE_URL` (default: `http://localhost:11434`)
- `DATABASE_URL` (default: `sqlite:///./events.db`)
- `SCRAPE_DAYS_AHEAD` (default: `60`)
