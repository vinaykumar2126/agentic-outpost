"""Reddit community-event discovery connector (Feature 2).

Reddit is the discovery layer for community-driven / word-of-mouth events that
Luma and AIcamp miss; the existing pipeline does the ranking and emailing.

Retrieval uses Reddit's public RSS/Atom feeds (search.rss / hot.rss / <post>.rss).
Reddit's Data API now requires per-use-case approval (Responsible Builder Policy,
Nov 2025) with multi-week waits, but RSS remains an intentionally public
syndication surface: no OAuth, full post bodies (the old MCP path truncated to
300 chars), and exact ISO timestamps. We keep it polite — descriptive User-Agent,
~1s between requests, ~20 fetches once per night.

Pipeline (token-disciplined, deep-agents style):
  1. RETRIEVE  — narrow search feeds (subreddit scope + OR-combined queries +
                 sort=new/t=week) + "events/what's happening" megathread comments.
                 Raw XML is saved to .agent/scratch/reddit_raw/, never in LLM context.
  2. TRIM      — trim_post() projects each candidate to a minimal dict in code.
  3. EXTRACT   — one recall-biased Groq JSON pass over the trimmed survivors.
  4. ENRICH    — lu.ma out-links are re-scraped with the existing Playwright
                 connector for structured details instead of parsing prose.
  5. DEDUP     — against events already in the DB (cross-posted Luma/AIcamp events)
                 by resolved URL, falling back to normalized (title + date).
"""

import asyncio
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup
from groq import Groq
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import settings
from app.connectors.base import EventConnector, RawEvent
from app.llm import chunk_by_chars, groq_json_chat

logger = logging.getLogger(__name__)

PACIFIC = ZoneInfo("America/Los_Angeles")
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

REDDIT_BASE = "https://www.reddit.com"
# Reddit UA convention: <platform>:<app id>:<version> (purpose)
USER_AGENT = "macos:events-finder:v1.0 (personal Bay Area AI events aggregator, read-only RSS)"
# Unauthenticated RSS is limited to ~10 req/min with burst accounting over a longer
# window (repeated dev runs from the same IP drain the same bucket). This runs from a
# 2am cron where slow minutes cost nothing, so stay comfortably under the limit and
# back off hard when throttled.
_REQUEST_DELAY_S = 10.0
_MAX_RETRIES_429 = 2
_429_FALLBACK_BACKOFF_S = 61.0   # when Reddit sends no Retry-After header
_429_PENALTY_STEP_S = 30.0       # added to the inter-request delay after an exhausted 429

# r/SFtech is private — Reddit returns HTTP 403 for it on every surface, so it's dropped.
GENERAL_SUBREDDITS = ["sanfrancisco", "bayarea", "sanfranciscobayarea"]

# AI-niche subs: generic terms like "agents OR LLM" match the entire subreddit there,
# flooding retrieval (and the LLM token budget) with non-event posts. Anchor on location
# instead — in r/LocalLLaMA, a post mentioning SF is almost always a meetup announcement.
NICHE_SUBREDDITS = ["LocalLLaMA", "artificial"]

SUBREDDITS = GENERAL_SUBREDDITS + NICHE_SUBREDDITS  # megathread scan covers all

# OR-combined so 8 spec queries cost 2 feed fetches per subreddit instead of 8
SEARCH_QUERIES = [
    '"AI meetup" OR "AI event" OR hackathon OR "demo night"',
    'agents OR LLM OR "build night" OR coworking',
]
NICHE_QUERIES = ['"San Francisco" OR "Bay Area" OR "SF meetup" OR "SF event"']

_MEGATHREAD_RE = re.compile(r"\b(events?|happening|weekly|monthly|what'?s on)\b", re.IGNORECASE)

# lu.ma first (it gets structured enrichment); partiful/eventbrite still count as event links
_EVENT_LINK_RE = re.compile(
    r"https?://(?:www\.)?(?:lu\.ma|luma\.com|partiful\.com|eventbrite\.com)/[^\s)\]\"'<>&]+",
    re.IGNORECASE,
)

_POST_LINK_RE = re.compile(r"reddit\.com(/r/([^/]+)/comments/([a-z0-9]+)/[^\s\"]*)")

_MAX_CANDIDATES = 30       # cap on posts that reach the LLM
_MAX_MEGATHREADS = 4
_MAX_COMMENT_CANDIDATES = 20
_BODY_CAP = 1500           # per-post body cap before the LLM sees it

# Groq free tier is TPM-limited (6k/min for llama-3.3-70b). ~9k chars ≈ 2.5k tokens
# per call keeps each request well under budget; the gap spreads calls across minutes.
_EXTRACT_CHAR_BUDGET = 9000
_LLM_CALL_GAP_S = 25.0

# Raw feed XML goes here for audit — never into LLM context
RAW_DUMP_DIR = Path(__file__).resolve().parents[3] / ".agent" / "scratch" / "reddit_raw"


# ── Pure helpers (unit-testable without network) ─────────────────────────────

def extract_urls(text: str) -> List[str]:
    """Pull luma/partiful/eventbrite event links out of free text or HTML."""
    if not text:
        return []
    seen: set[str] = set()
    urls = []
    for url in _EVENT_LINK_RE.findall(text):
        url = url.rstrip(".,;:!?")
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def html_to_text(html: str) -> str:
    """Strip Reddit's RSS content HTML down to plain text, dropping the
    'submitted by /u/x [link] [comments]' boilerplate footer."""
    if not html:
        return ""
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    return re.sub(r"submitted by\s+/u/\S+.*$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()


def trim_post(raw: dict) -> dict:
    """Project a fat post dict to the minimal shape the LLM sees (~5-10x token cut).

    URL scan covers content_html too: for link posts the outbound event URL only
    exists as an href attribute, which plain-text stripping would discard.
    """
    body = raw.get("selftext") or ""
    url_haystack = " ".join(
        filter(None, [raw.get("title", ""), body, raw.get("link_url") or "", raw.get("content_html") or ""])
    )
    return {
        "sub": raw.get("subreddit", ""),
        "title": raw.get("title", ""),
        "body": body[:_BODY_CAP],
        "url": raw.get("url", ""),
        "created_utc": raw.get("created_utc"),
        "out_links": extract_urls(url_haystack),
    }


def parse_feed(xml_text: str) -> List[dict]:
    """Parse a Reddit Atom feed (search.rss / hot.rss / <post>.rss) into candidate dicts."""
    if not xml_text or not xml_text.strip():
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("Feed XML parse failed: %s", exc)
        return []

    candidates = []
    for entry in root.findall("atom:entry", _ATOM_NS):
        title_el = entry.find("atom:title", _ATOM_NS)
        link_el = entry.find("atom:link", _ATOM_NS)
        published_el = entry.find("atom:published", _ATOM_NS)
        content_el = entry.find("atom:content", _ATOM_NS)
        if title_el is None or link_el is None:
            continue

        link = link_el.get("href", "")
        m = _POST_LINK_RE.search(link)
        created_utc: Optional[float] = None
        if published_el is not None and published_el.text:
            try:
                created_utc = datetime.fromisoformat(published_el.text).timestamp()
            except ValueError:
                pass

        content_html = content_el.text or "" if content_el is not None else ""
        candidates.append({
            "title": (title_el.text or "").strip(),
            "permalink": link,
            "subreddit": m.group(2) if m else "",
            "post_id": m.group(3) if m else "",
            "created_utc": created_utc,
            "content_html": content_html,
            "selftext": html_to_text(content_html),
        })
    return candidates


def comment_candidates_from_feed(entries: List[dict], thread: dict) -> List[dict]:
    """Turn a <post>.rss feed into comment candidates. Entry 0 is the post itself;
    comment entries are titled '/u/<author> on <post title>'."""
    out = []
    for idx, e in enumerate(entries):
        if not e["title"].startswith("/u/"):
            continue  # the post entry, not a comment
        if e["title"].lower().startswith("/u/automoderator"):
            continue
        body = e["selftext"]
        if len(body) <= 30:  # "thanks!" noise
            continue
        out.append({
            "post_id": f"{thread['post_id']}_c{idx}",
            "subreddit": thread["subreddit"],
            "title": f"[comment in: {thread['title']}]",
            "selftext": body,
            "content_html": e.get("content_html", ""),
            "permalink": thread["permalink"],
            "created_utc": e.get("created_utc") or thread.get("created_utc"),
        })
    return out


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def dedup_against_existing(extracted: List[dict], existing_urls: set[str],
                           existing_title_dates: set[tuple[str, str]]) -> List[dict]:
    """Drop events already known to the DB (cross-posted Luma/AIcamp events) and
    intra-batch duplicates. Key: resolved URL; fallback: normalized (title, date)."""
    kept: List[dict] = []
    seen_urls: set[str] = set()
    seen_title_dates: set[tuple[str, str]] = set()
    for ev in extracted:
        url = (ev.get("resolved_url") or "").rstrip("/")
        date_str = (ev.get("date_iso") or "")[:10]
        td_key = (normalize_title(ev.get("name", "")), date_str)
        if url and (url in existing_urls or url in seen_urls):
            continue
        if td_key[0] and (td_key in existing_title_dates or td_key in seen_title_dates):
            continue
        if url:
            seen_urls.add(url)
        if td_key[0]:
            seen_title_dates.add(td_key)
        kept.append(ev)
    return kept


def _dump_raw(name: str, text: str) -> None:
    """Audit trail on disk; failure here must never break the scrape."""
    try:
        RAW_DUMP_DIR.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)[:120]
        (RAW_DUMP_DIR / f"{safe}.xml").write_text(text)
    except OSError as exc:
        logger.debug("Raw dump failed for %s: %s", name, exc)


# ── LLM extraction (recall-biased, one JSON-mode call) ───────────────────────

EXTRACTION_SYSTEM_PROMPT = """You extract real-world event announcements from Reddit posts.
Context: the reader hunts Bay Area AI/tech community events (meetups, hackathons, demo nights,
build nights, coworking sessions) — including semi-private, word-of-mouth ones.

From each post, extract any concrete upcoming event. Rules:
- Use the post's created timestamp (provided per post) to resolve relative dates like
  "this Saturday" or "next Thursday". Dates without a year mean the next occurrence.
- Emit date_iso as ISO 8601 local Pacific time, e.g. "2026-07-25T18:00". If the post gives
  a day but no time, use 18:00. If no resolvable date, set date_iso to null.
- is_ai_relevant: judge SEMANTICALLY — community posts rarely use clean tags. A hacker
  coworking night or an indie demo night where people show projects counts as plausibly
  AI-relevant. Bias toward INCLUDING plausible events (recall over precision) and express
  doubt via confidence (0.0-1.0) instead of dropping them. Only mark is_ai_relevant false
  when the event clearly has nothing to do with AI/tech (e.g. a hiking group, a concert).
- source_url: an event-page link (lu.ma, partiful, eventbrite) found in that post, else null.
- A post may contain zero, one, or several events. Posts that are not event announcements
  (rants, questions, news) yield zero events.

Return ONLY a JSON object: {"events": [{"name", "date_iso", "location", "organizer",
"is_ai_relevant", "confidence", "source_url", "post_url"}]} — post_url is the reddit
permalink of the post the event came from. No markdown fences."""


# ── Connector ────────────────────────────────────────────────────────────────

class RedditConnector(EventConnector):
    source_name = "reddit"

    def is_available(self) -> bool:
        """RSS needs no credentials — just confirm Reddit's feed endpoint answers."""
        try:
            resp = httpx.get(
                f"{REDDIT_BASE}/r/bayarea/new.rss?limit=1",
                headers={"User-Agent": USER_AGENT},
                timeout=8,
                follow_redirects=True,
            )
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def fetch_events(self, days_ahead: int = 60) -> List[RawEvent]:
        candidates = await self._retrieve_candidates()
        if not candidates:
            logger.info("RedditConnector: no candidates retrieved")
            return []

        trimmed = [trim_post(c) | {"permalink": c["permalink"]} for c in candidates]
        extracted = self._extract_events_llm(trimmed)
        logger.info("RedditConnector: LLM extracted %d candidate events from %d posts",
                    len(extracted), len(trimmed))

        extracted = self._filter_and_resolve(extracted, days_ahead)
        extracted = self._dedup_against_db(extracted)
        events = await self._enrich_and_build(extracted)
        logger.info("RedditConnector fetched %d events", len(events))
        return events

    # ── Stage 1: retrieval via public RSS feeds ──────────────────────────────

    async def _retrieve_candidates(self) -> List[dict]:
        by_id: dict[str, dict] = {}
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, timeout=15, follow_redirects=True
        ) as client:
            # 1a. Narrow keyword search per subreddit — search IS the first filter
            sub_queries = [(s, SEARCH_QUERIES) for s in GENERAL_SUBREDDITS] + \
                          [(s, NICHE_QUERIES) for s in NICHE_SUBREDDITS]
            for sub, queries in sub_queries:
                for qi, query in enumerate(queries):
                    url = (f"{REDDIT_BASE}/r/{sub}/search.rss"
                           f"?q={quote(query)}&restrict_sr=on&sort=new&t=week&limit=25")
                    xml_text = await self._fetch(client, url, f"search_{sub}_q{qi}")
                    for cand in parse_feed(xml_text):
                        if cand["post_id"]:
                            by_id.setdefault(cand["post_id"], cand)

            # Newest first, cap before the LLM stage
            candidates = sorted(by_id.values(),
                                key=lambda c: c.get("created_utc") or 0, reverse=True)
            candidates = candidates[:_MAX_CANDIDATES]

            # 1b. Megathreads ("weekly events", "what's happening") + their comments
            comment_cands = await self._collect_megathread_comments(client, set(by_id))
            candidates += comment_cands[:_MAX_COMMENT_CANDIDATES]

        return candidates

    async def _collect_megathread_comments(self, client: httpx.AsyncClient,
                                           known_ids: set[str]) -> List[dict]:
        threads: List[dict] = []
        # "What's happening" megathreads live in the city subs, not the AI-niche ones —
        # skipping the niche subs here saves requests from the rate-limit bucket
        for sub in GENERAL_SUBREDDITS:
            xml_text = await self._fetch(client, f"{REDDIT_BASE}/r/{sub}/hot.rss?limit=10",
                                         f"hot_{sub}")
            threads += [c for c in parse_feed(xml_text)
                        if c["post_id"] and _MEGATHREAD_RE.search(c["title"])]

        comment_cands: List[dict] = []
        for thread in threads[:_MAX_MEGATHREADS]:
            feed_url = thread["permalink"].rstrip("/") + "/.rss?limit=40&sort=top"
            xml_text = await self._fetch(client, feed_url, f"comments_{thread['post_id']}")
            entries = parse_feed(xml_text)
            comment_cands += [c for c in comment_candidates_from_feed(entries, thread)
                              if c["post_id"] not in known_ids]
        return comment_cands

    async def _fetch(self, client: httpx.AsyncClient, url: str, dump_name: str) -> str:
        """One polite feed fetch with 429 backoff; failures degrade to an empty feed,
        never abort the run. Exhausted 429s permanently slow the rest of the run
        (adaptive penalty) — the bucket is clearly drained, so stop hammering it."""
        await asyncio.sleep(_REQUEST_DELAY_S + getattr(self, "_delay_penalty_s", 0.0))
        for attempt in range(_MAX_RETRIES_429 + 1):
            try:
                resp = await client.get(url)
            except httpx.HTTPError as exc:
                logger.warning("Feed fetch failed for %s: %s", url, exc)
                return ""
            if resp.status_code == 200:
                _dump_raw(dump_name, resp.text)
                return resp.text
            if resp.status_code == 429 and attempt < _MAX_RETRIES_429:
                # Respect Retry-After when Reddit sends it; otherwise back off hard
                retry_after = float(resp.headers.get("retry-after")
                                    or _429_FALLBACK_BACKOFF_S * (attempt + 1))
                logger.info("429 on %s — backing off %.0fs", url, retry_after)
                await asyncio.sleep(retry_after)
                continue
            if resp.status_code == 429:
                self._delay_penalty_s = getattr(self, "_delay_penalty_s", 0.0) + _429_PENALTY_STEP_S
                logger.warning("Feed fetch %s -> HTTP 429 after retries; slowing rest of run "
                               "(+%.0fs/request)", url, self._delay_penalty_s)
            else:
                logger.warning("Feed fetch %s -> HTTP %d", url, resp.status_code)
            return ""
        return ""

    # ── Stage 3: extraction ──────────────────────────────────────────────────

    def _extract_events_llm(self, trimmed: List[dict]) -> List[dict]:
        payload = []
        for t in trimmed:
            created = t.get("created_utc")
            created_str = (
                datetime.fromtimestamp(created, tz=PACIFIC).strftime("%A %Y-%m-%d %H:%M %Z")
                if created else "unknown"
            )
            payload.append({
                "post_url": t["permalink"],
                "sub": t["sub"],
                "posted_at": created_str,   # anchors relative dates like "this Saturday"
                "title": t["title"],
                "body": t["body"],
                "links_in_post": t["out_links"],
            })

        client = Groq(api_key=settings.groq_api_key)
        today = datetime.now(PACIFIC).strftime("%A %Y-%m-%d")
        events: List[dict] = []
        # Chunked so each request stays far below Groq's TPM budget
        batches = chunk_by_chars(payload, _EXTRACT_CHAR_BUDGET)
        for i, batch in enumerate(batches):
            if i:
                time.sleep(_LLM_CALL_GAP_S)
            user_prompt = (
                f"Today is {today}. "
                f"Extract events from these {len(batch)} Reddit posts.\n\n"
                f"{json.dumps(batch, indent=1)}"
            )
            try:
                content = groq_json_chat(
                    client,
                    model=settings.groq_model,
                    messages=[
                        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                events += json.loads(content).get("events", [])
            except Exception as exc:
                logger.error("Extraction batch %d/%d failed: %s", i + 1, len(batches), exc)
        return events

    # ── Stages 4-5: resolve, dedup, enrich, assemble ─────────────────────────

    def _filter_and_resolve(self, extracted: List[dict], days_ahead: int) -> List[dict]:
        now = datetime.now(PACIFIC)
        kept = []
        for ev in extracted:
            if ev.get("is_ai_relevant") is False:
                continue
            if not ev.get("date_iso"):
                continue  # RawEvent requires start_datetime; undateable events can't be stored
            try:
                dt = datetime.fromisoformat(ev["date_iso"])
            except (ValueError, TypeError):
                logger.debug("Unparseable date_iso %r for %r", ev.get("date_iso"), ev.get("name"))
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=PACIFIC)
            if not (now - timedelta(days=1) <= dt <= now + timedelta(days=days_ahead)):
                continue
            ev["start_dt_utc"] = dt.astimezone(timezone.utc).replace(tzinfo=None)
            source_url = ev.get("source_url") or ""
            ev["resolved_url"] = source_url if _EVENT_LINK_RE.match(source_url) else ev.get("post_url", "")
            kept.append(ev)
        return kept

    def _dedup_against_db(self, extracted: List[dict]) -> List[dict]:
        from app.database import SessionLocal
        from app.models import Event

        db = SessionLocal()
        try:
            rows = db.query(Event.url, Event.title, Event.start_datetime).all()
        finally:
            db.close()
        existing_urls = {(r[0] or "").rstrip("/") for r in rows}
        existing_title_dates = {
            (normalize_title(r[1]), r[2].strftime("%Y-%m-%d") if r[2] else "") for r in rows
        }
        deduped = dedup_against_existing(extracted, existing_urls, existing_title_dates)
        if len(deduped) < len(extracted):
            logger.info("RedditConnector: dedup dropped %d already-known events",
                        len(extracted) - len(deduped))
        return deduped

    async def _enrich_and_build(self, extracted: List[dict]) -> List[RawEvent]:
        events: List[RawEvent] = []
        luma_targets = [ev for ev in extracted
                        if re.search(r"lu\.ma|luma\.com", ev.get("resolved_url", ""))]

        enriched_by_url: dict[str, RawEvent] = {}
        if luma_targets:
            enriched_by_url = await self._scrape_luma_details([ev["resolved_url"] for ev in luma_targets])

        for ev in extracted:
            url = ev["resolved_url"]
            scraped = enriched_by_url.get(url)
            post_id_part = (ev.get("post_url") or "").rstrip("/").split("/")[-2:-1]
            external_id = f"r_{post_id_part[0] if post_id_part else normalize_title(ev.get('name',''))[:40].replace(' ', '_')}_{ev.get('start_dt_utc').strftime('%Y%m%d')}"

            if scraped:
                # Structured details from the event page beat prose parsing
                events.append(RawEvent(
                    external_id=external_id,
                    source=self.source_name,
                    title=scraped.title,
                    description=scraped.description,
                    url=url,
                    start_datetime=scraped.start_datetime,
                    end_datetime=scraped.end_datetime,
                    location_name=scraped.location_name,
                    location_address=scraped.location_address,
                    is_online=scraped.is_online,
                    organizer_name=scraped.organizer_name or ev.get("organizer"),
                    tags=(scraped.tags or []) + ["community", "via-reddit"],
                    is_free=scraped.is_free,
                    price_min=scraped.price_min,
                ))
            else:
                blob = f"{ev.get('name','')} {ev.get('location') or ''}"
                events.append(RawEvent(
                    external_id=external_id,
                    source=self.source_name,
                    title=ev.get("name", "Untitled community event"),
                    description=(
                        f"Community event found on Reddit (confidence {ev.get('confidence', 0):.1f}). "
                        f"Source post: {ev.get('post_url', '')}"
                    ),
                    url=url,
                    start_datetime=ev["start_dt_utc"],
                    location_name=ev.get("location"),
                    is_online=bool(re.search(r"\b(online|virtual|zoom|remote)\b", blob, re.IGNORECASE)),
                    organizer_name=ev.get("organizer"),
                    tags=["community", "via-reddit"],
                    is_free=True,
                ))
        return events

    async def _scrape_luma_details(self, urls: List[str]) -> dict[str, RawEvent]:
        """Reuse the existing Playwright detail scraper: Reddit discovers, Luma scraper enriches."""
        from app.connectors.luma import LumaConnector

        luma = LumaConnector()
        if not luma.is_available():
            logger.info("Playwright MCP unavailable — skipping lu.ma enrichment")
            return {}

        enriched: dict[str, RawEvent] = {}
        server_params = StdioServerParameters(command="npx", args=["@playwright/mcp", "--headless"])
        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    for url in urls:
                        try:
                            scraped = await luma._scrape_event_detail(session, url)
                            if scraped:
                                enriched[url] = scraped
                        except Exception as exc:
                            logger.warning("lu.ma enrichment failed for %s: %s", url, exc)
        except Exception as exc:
            logger.warning("Playwright session for enrichment failed: %s", exc)
        return enriched
