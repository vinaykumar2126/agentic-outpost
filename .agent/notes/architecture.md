# Architecture notes — for RedditConnector (Feature 2)

Distilled from base.py, luma.py, aicamp.py, registry.py, jobs.py, email.py.
Work from THIS file; don't re-read the big files each turn.

## RawEvent schema (connectors/base.py) — the exact output contract
```python
@dataclass
class RawEvent:
    external_id: str          # unique within source; used in UNIQUE(source, external_id)
    source: str               # -> set to "reddit"
    title: str
    description: str
    url: str
    start_datetime: datetime  # UTC, tz-naive (see _parse_dt convention below)
    end_datetime: Optional[datetime] = None
    location_name: Optional[str] = None
    location_address: Optional[str] = None
    is_online: bool = False
    organizer_name: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    is_free: bool = True
    price_min: Optional[float] = None
    price_max: Optional[float] = None
```
Datetimes stored tz-NAIVE UTC: `dt.astimezone(timezone.utc).replace(tzinfo=None)`.

## EventConnector ABC (connectors/base.py)
- class attr `source_name: str`
- `async def fetch_events(self, days_ahead: int = 60) -> List[RawEvent]` — idempotent
- `def is_available(self) -> bool` — checked at startup; missing deps => skipped gracefully

## LumaConnector pattern (the enrichment scraper I will reuse)
- Spawns `@playwright/mcp --headless` via `StdioServerParameters(command="npx", args=["@playwright/mcp","--headless"])`
  inside `async with stdio_client(...) as (read,write): async with ClientSession(...) as session: await session.initialize()`
- MCP tools used: `browser_navigate {url}`, `browser_snapshot {}`, `browser_evaluate {function}`
- `_scrape_event_detail(session, url)`: tries `window.__NEXT_DATA__...initialData` first (Luma is Next.js),
  falls back to snapshot parsing. **This is the "enrich a lu.ma/partiful URL" path I feed out_links into.**
- `external_id = url.rstrip("/").split("/")[-1]`
- `_extract_text(tool_result)`: pulls `.content[].text` from an MCP tool result. Copy this helper.

## registry.py — registration (one line)
```python
from app.connectors.reddit import RedditConnector
CONNECTOR_REGISTRY = { "luma": LumaConnector, "aicamp": AicampConnector, "reddit": RedditConnector }
```
`get_active_connectors()` instantiates each and keeps those where `is_available()` is True.

## jobs.py — nightly_scrape_job()
- Loops `get_active_connectors()`; per connector: creates ScrapeRun, `asyncio.run(connector.fetch_events())`,
  `upsert_events(db, raw_events, run)`, then `EventRanker().rank_unscored(db)`.
- upsert dedups by `(source, external_id)`; re-rank triggered only if title/description changed.
- After ALL connectors: `send_scrape_summary(db, job_started_at)`.
- **No changes needed to email trigger or ranking** — Reddit events flow through automatically once registered.
- NOTE: dedup in upsert is per-(source,external_id), so cross-source dedup (Reddit event that is
  really a Luma event) must happen INSIDE RedditConnector before returning — resolve out_link -> luma,
  and either skip if it collides, or return with source-appropriate id. Design decision below.

## email.py (notifications)
- `send_scrape_summary` selects events with `created_at >= job_started_at AND relevance_score >= _MIN_SCORE (5.0)`.
  (Spec text says >=5; actual code gate is 5.0 — flag but don't change unless asked.)
- Shows title, score, date, location, organizer, url, justification. Sorted by score desc.
- To make Reddit events "visibly distinct": source column exists on Event; could surface `source` in email body
  (small optional enhancement to _format_body).

## Ranker (ranking/event_ranker.py) — already Groq, JSON mode, batches of 20. No changes needed.

## Deep-agents / token discipline for THIS feature
- Retrieval narrows BEFORE LLM: subreddit scope + search queries + sort=new,time=week.
- trim_post() projects raw fat Reddit JSON -> {sub,title,body[:1500],url,created_utc,out_links} in CODE.
- Save untrimmed raw to .agent/scratch/reddit_raw/<query>.json; keep only trimmed in context.
- ONE structured-output LLM extraction pass over trimmed candidates, recall-biased:
  emit {name,date,location,organizer,is_ai_relevant,confidence,source_url}; pass created_utc for relative dates.
- Enrich: if out_links has luma/partiful/eventbrite -> feed URL to Playwright scraper for structured detail.
- Dedup by resolved event URL, fallback normalized (title+date). Tag source="reddit".

## SUPERSEDED 2026-07-19: retrieval pivoted from reddit-mcp-server to public RSS.
Reddit's Data API now needs per-use-case approval (Responsible Builder Policy, Nov 2025;
multi-week waits, personal projects often rejected). Public Atom feeds still work from the
user's residential IP: /r/<sub>/search.rss, hot.rss, <post>/.rss — full bodies, ISO timestamps,
no auth. Limits: ~10 req/min unauthenticated → 7s delay + 429 backoff in connector.
Only Stage 1 (RETRIEVE) changed; trim/extract/enrich/dedup untouched. No Reddit creds in config.

## (old) Reddit MCP — CONFIRMED (jordanburke/reddit-mcp-server, user-approved)
- Launch: `StdioServerParameters(command="npx", args=["-y","reddit-mcp-server"], env={REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET})`
- Anonymous mode → HTTP 403 on every endpoint (verified live). Read-only OAuth via
  REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET (free "script" app at reddit.com/prefs/apps). No password needed.
- Full tool schemas dumped to .agent/scratch/reddit_mcp_tools.json. The ones we use:
  - search_reddit(query, subreddit?, sort[relevance|hot|top|new|comments], time_filter[hour..all], limit 1-100, type[link|sr|user], after?)
  - get_reddit_post(subreddit, post_id)
  - browse_subreddit(subreddit?, sort?, time_filter?, limit?, after?)
  - get_post_comments(post_id, subreddit, sort?, limit?)
- Output is MARKDOWN, not JSON (verified from bundled dist/index.js):
  - search_reddit item block:
    `### N. <title>` / `- Subreddit: r/<sub>` / `- Author: u/<a>` / `- Score: n (x% upvoted)` /
    `- Comments: n` / `- Posted: <toLocaleString e.g. 7/15/2026, 5:00:00 PM>` /
    `- Link: https://reddit.com/r/<sub>/comments/<post_id>/<slug>/`
  - get_reddit_post: `# Post from r/<sub>` ... `## Content\n<content>\n\n## Stats` ...
    **content truncated to 300 chars**; for LINK posts content == the outbound URL (goldmine for out_links);
    `- Title: <t>` under `## Post Details`; `- Type: Text Post|Link Post`
  - get_post_comments: header block then per-comment `**u/<a>** (n points)\n\n<body>\n\n---`
    (comment bodies NOT truncated)
- 300-char selftext truncation tradeoff: title+300 chars is enough for recall-biased extraction;
  links usually appear early or the post IS a link post; megathread comments come through full.

## Retrieval budget (authenticated ~60-100 req/min)
2 OR-combined queries × 6 subs = 12 search calls + ~6 browse (megathread discovery)
+ ≤25 get_reddit_post hydrations + ≤4 get_post_comments = ~45 calls/night. Fine.

## Config additions
Settings: reddit_client_id, reddit_client_secret (empty default => is_available False => graceful skip).
```
