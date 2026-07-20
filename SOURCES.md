# SOURCES.md

## Add feature 1
 ** Add a new event connector for aicamp.ai that scrapes events using the existing MCP Playwright setup — the same pattern as LumaConnector in luma.py. The connector should:

    - Navigate to https://www.aicamp.ai/ and discover event listing pages
    - Collect individual event URLs by parsing the MCP accessibility tree snapshot
    - Visit each event detail page and extract: title, date/time, location, description, organizer, and URL
    - Return a list of RawEvent objects (same schema as Luma)
    - Be registered in registry.py so it's picked up automatically by the scheduler and ranker

 ** After the nightly cron job completes successfully, send a summary email to godavartivinaykumar@gmail.com with the day's newly scraped and ranked events.

    The email should:

    Only include new or updated events from that night's run (not the full DB)
    Show events sorted by relevance score (highest first)
    Include for each event: title, score, date, location, organizer, and URL
    Only send if there are events with a score ≥ 7 (no email if nothing interesting was found)
    Be triggered at the end of nightly_scrape_job() in jobs.py, after ranking completes
    I've the gmail mcp server you can check it out

# Add feature 2 — Reddit community-event discovery connector

## Goal
Add a new event source that surfaces the **community-driven, semi-private, and
word-of-mouth** events that Luma and AIcamp miss. Reddit is the discovery layer;
the existing pipeline does the ranking and emailing. Events must merge into the
same nightly flow and the same summary email.

---

## How to work on this task (agent operating instructions)

Follow the deep-agents workflow. Do NOT try to hold everything in your context —
plan explicitly, offload aggressively, and re-orient often.

### 1. Plan first with `write_todos`
Before writing any code, call `write_todos` with a concrete plan. Start from this
list and refine it once you've read the codebase:

- [ ] Read CLAUDE.md, FLOW.md, luma.py, registry.py, jobs.py; capture reusable
      details into scratch notes (see step 2)
- [ ] Scaffold `reddit.py` with a `RedditConnector` mirroring `LumaConnector`
- [ ] Implement narrow retrieval (subreddit scoping + search + recency)
- [ ] Implement the `trim_post` projection layer (field trimming)
- [ ] Implement the LLM extraction pass (structured output, recall-biased)
- [ ] Implement link-out enrichment (feed luma/partiful URLs into existing scraper)
- [ ] Dedup Reddit events against existing sources
- [ ] Register `RedditConnector` in registry.py
- [ ] Wire into `nightly_scrape_job()` and confirm Reddit events reach the email
- [ ] End-to-end test on a week of real data

### 2. Offload context to the filesystem
- As you read large files (CLAUDE.md, FLOW.md, luma.py), write ONLY the details
  you'll reuse into `.agent/notes/architecture.md`: the exact `RawEvent` schema
  fields, `LumaConnector`'s method names/signatures, the registry registration
  call, and where/how `nightly_scrape_job()` invokes connectors. After that, work
  from your notes — do not re-read the whole files on every turn.
- While testing retrieval, write raw Reddit tool output to
  `.agent/scratch/reddit_raw/<query>.json` and work from a trimmed preview
  (first ~10 lines + a "N more" line), never the full blob in context.

### 3. Re-orient with `read_todos`
After any context-heavy step (reading a big file, a large tool result), call
`read_todos` and restate what's done vs. next. This keeps you current and stops
you from repeating work or losing the thread across a long task.

### 4. If anything is unclear
Check CLAUDE.md and FLOW.md first. If still unclear, ask me before guessing —
especially about the connector interface or the `RawEvent` schema.

---

## Feature spec

### Retrieval — narrow BEFORE anything reaches the LLM
Search is your first and cheapest filter. Do not dump whole subreddits.

- **Reddit MCP:** use my configured Reddit MCP server. **Confirm its exact name and
  tool schema with me before wiring it in** (I'll tell you which one). Follow the
  same MCP-call pattern the Playwright connector uses.
- **Subreddits:** r/sanfrancisco, r/bayarea, r/sanfranciscobayarea, r/SFtech, plus
  AI-niche subs (e.g. r/LocalLLaMA, r/artificial) where SF meetups get posted.
- **Search queries** (run several): "AI meetup", "hackathon", "agents", "demo
  night", "LLM", "AI event", "coworking", "build night".
- **Recency:** `sort=new`, `time=week`. Also pull any pinned/weekly "events" or
  "what's happening" megathreads and their top-level comments.

### Trim — project fields in code, not by asking the LLM
A raw Reddit object is fat (awards, flair, edit history, nested reply metadata).
Strip it to a minimal shape in code before the model sees it:

```python
def trim_post(raw):
    return {
        "sub": raw["subreddit"],
        "title": raw["title"],
        "body": raw["selftext"][:1500],          # cap runaway walls of text
        "url": raw["url"],
        "created_utc": raw["created_utc"],        # needed to resolve "this Saturday"
        "out_links": extract_urls(raw["selftext"]) # luma / lu.ma / partiful / eventbrite
    }
```

This typically cuts per-post tokens ~5–10x. Save the untrimmed originals to
`.agent/scratch/reddit_raw/` for audit; send only trimmed objects downstream.

### Extract — LLM pass on survivors only, recall-biased
Run one structured-output extraction over the trimmed candidates. Emit:
`{name, date, location, organizer, is_ai_relevant, confidence, source_url}`.

- **Pass `created_utc`** to the model so it can resolve relative dates
  ("Thursday", "next weekend") correctly.
- **Do NOT hard-gate on keywords here.** Community events rarely use clean tags
  like "AI Engineering." Judge relevance semantically and bias toward *recall* —
  include plausible community events with a `confidence` score rather than
  dropping them. Precision is recovered later by the existing ≥7 ranking gate.

### Enrich — treat Reddit as a discovery layer
Many community posts link out to a Luma/Partiful/Eventbrite page. When `out_links`
contains one, **feed that URL into the existing Playwright connector to extract
structured details**, instead of parsing the messy prose. Reddit finds the
long-tail event; your current scraper enriches it. This also sidesteps most
date-parsing fragility.

### Dedup — before merging
People cross-post their Luma events to Reddit, so collisions with existing
sources are expected. Dedup by resolved event URL, falling back to normalized
`(title + date)`. Never let the email repeat an event that Luma/AIcamp already
surfaced.

### Output shape
Return a list of `RawEvent` objects — **identical schema to Luma** — so the
ranker and email code need no changes. Tag the source as `reddit` (or
`community`) on each event so Reddit-sourced additions are visibly distinct in
the email.

### Registration & wiring
- Register `RedditConnector` in **registry.py** so the scheduler/ranker pick it
  up automatically.
- Ensure it runs inside **`nightly_scrape_job()` in jobs.py**, alongside Luma and
  AIcamp, before ranking. No changes to the email trigger or the ≥7 threshold —
  Reddit events flow through the existing summary email to
  godavartivinaykumar@gmail.com.

---

## Token budget check (why this design)
Raw pull of ~100 posts ≈ 60–80k tokens. Search-narrowing → ~25 candidates;
field projection → ~200 tokens each (~5k total) is all that reaches the
extraction call. Raw blobs live on disk, not in context.

- If you get any doubt pls look at CLAUDE.md and FLOW.md from the root of the project. If you still have any questions pls fell free to ask me.

- Please implement the Reddit feature completely, following the exact plan outlined under 'Add Feature 2' in SOURCES.md. Make sure to test each part as you build it so we don't end up with a broken app at the end. Let me know if you have any questions along the way.