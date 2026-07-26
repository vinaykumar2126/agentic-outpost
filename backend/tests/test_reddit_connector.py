import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.connectors.base import RawEvent
from app.connectors.reddit import (
    RedditConnector,
    comment_candidates_from_feed,
    dedup_against_existing,
    extract_urls,
    html_to_text,
    normalize_title,
    parse_feed,
    trim_post,
)
from app.models import Event

# ── Fixtures mirroring Reddit's real Atom feed shapes ────────────────────────

SEARCH_FEED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>search results</title>
  <entry>
    <author><name>/u/builder123</name></author>
    <title>AI Builders Demo Night this Thursday</title>
    <link href="https://www.reddit.com/r/bayarea/comments/abc123/ai_builders_demo_night/"/>
    <published>2026-07-15T17:00:00+00:00</published>
    <content type="html">&lt;div class="md"&gt;&lt;p&gt;Come demo your agents! Thursday 6pm at Founders Space. RSVP: &lt;a href="https://lu.ma/ai-demo-night"&gt;lu.ma/ai-demo-night&lt;/a&gt;&lt;/p&gt;&lt;/div&gt; submitted by /u/builder123 &lt;a href="https://lu.ma/ai-demo-night"&gt;[link]&lt;/a&gt; &lt;a href="https://www.reddit.com/r/bayarea/comments/abc123/x/"&gt;[comments]&lt;/a&gt;</content>
  </entry>
  <entry>
    <author><name>/u/hiker</name></author>
    <title>Weekly hiking group</title>
    <link href="https://www.reddit.com/r/bayarea/comments/def456/weekly_hiking_group/"/>
    <published>2026-07-14T09:30:00+00:00</published>
    <content type="html">&lt;div class="md"&gt;&lt;p&gt;Hike this weekend&lt;/p&gt;&lt;/div&gt;</content>
  </entry>
</feed>"""

COMMENTS_FEED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>What's happening this week?</title>
    <link href="https://www.reddit.com/r/sanfrancisco/comments/mega1/whats_happening/"/>
    <published>2026-07-14T08:00:00+00:00</published>
    <content type="html">&lt;p&gt;Post your events below&lt;/p&gt;</content>
  </entry>
  <entry>
    <title>/u/AutoModerator on What's happening this week?</title>
    <link href="https://www.reddit.com/r/sanfrancisco/comments/mega1/whats_happening/c001/"/>
    <content type="html">&lt;p&gt;I am a bot, this action was performed automatically and this line pads length&lt;/p&gt;</content>
  </entry>
  <entry>
    <title>/u/organizer on What's happening this week?</title>
    <link href="https://www.reddit.com/r/sanfrancisco/comments/mega1/whats_happening/c002/"/>
    <published>2026-07-14T10:00:00+00:00</published>
    <content type="html">&lt;p&gt;LLM paper reading group Saturday 2pm at the Mission library! Details: &lt;a href="https://lu.ma/llm-papers"&gt;here&lt;/a&gt;&lt;/p&gt;</content>
  </entry>
  <entry>
    <title>/u/someone on What's happening this week?</title>
    <link href="https://www.reddit.com/r/sanfrancisco/comments/mega1/whats_happening/c003/"/>
    <content type="html">&lt;p&gt;thanks!&lt;/p&gt;</content>
  </entry>
</feed>"""


# ── Feed parsing ─────────────────────────────────────────────────────────────

def test_parse_feed_search_results():
    cands = parse_feed(SEARCH_FEED_XML)
    assert len(cands) == 2
    first = cands[0]
    assert first["title"] == "AI Builders Demo Night this Thursday"
    assert first["post_id"] == "abc123"
    assert first["subreddit"] == "bayarea"
    assert first["created_utc"] is not None
    assert "Founders Space" in first["selftext"]
    # boilerplate footer stripped from text, but html kept for URL scanning
    assert "submitted by" not in first["selftext"]
    assert "lu.ma/ai-demo-night" in first["content_html"]


def test_parse_feed_bad_xml_returns_empty():
    assert parse_feed("this is not xml <<<") == []


def test_html_to_text_strips_tags_and_footer():
    html = '<div class="md"><p>Hello <b>world</b></p></div> submitted by /u/x <a href="y">[link]</a>'
    assert html_to_text(html) == "Hello world"


def test_comment_candidates_from_feed():
    entries = parse_feed(COMMENTS_FEED_XML)
    thread = {"post_id": "mega1", "subreddit": "sanfrancisco",
              "title": "What's happening this week?",
              "permalink": "https://www.reddit.com/r/sanfrancisco/comments/mega1/whats_happening/",
              "created_utc": 1752480000.0}
    cands = comment_candidates_from_feed(entries, thread)
    # post entry skipped, AutoModerator skipped, "thanks!" too short — one survivor
    assert len(cands) == 1
    assert "LLM paper reading group" in cands[0]["selftext"]
    assert cands[0]["post_id"].startswith("mega1_c")
    assert cands[0]["subreddit"] == "sanfrancisco"


# ── Trim + URL extraction ────────────────────────────────────────────────────

def test_extract_urls():
    text = "RSVP https://lu.ma/ai-demo-night. Also https://partiful.com/e/xyz789 and https://example.com/nope"
    urls = extract_urls(text)
    assert urls == ["https://lu.ma/ai-demo-night", "https://partiful.com/e/xyz789"]


def test_trim_post_caps_body_and_scans_html_for_links():
    raw = {
        "subreddit": "bayarea",
        "title": "Demo night",
        "selftext": "x" * 5000,
        "content_html": '<p>xxx</p> <a href="https://partiful.com/e/abc">[link]</a>',
        "url": "https://reddit.com/r/bayarea/comments/abc123/x/",
        "created_utc": 1750000000.0,
    }
    t = trim_post(raw)
    assert len(t["body"]) == 1500
    # event link only present as an href in the HTML is still collected
    assert "https://partiful.com/e/abc" in t["out_links"]
    assert t["sub"] == "bayarea"
    assert t["created_utc"] == 1750000000.0


def test_trim_post_from_real_feed():
    cand = parse_feed(SEARCH_FEED_XML)[0]
    t = trim_post(cand)
    assert "https://lu.ma/ai-demo-night" in t["out_links"]
    assert "Founders Space" in t["body"]


# ── Dedup ────────────────────────────────────────────────────────────────────

def test_dedup_drops_known_url_and_title_date():
    extracted = [
        {"name": "AI Demo Night", "date_iso": "2026-07-23T18:00", "resolved_url": "https://lu.ma/ai-demo-night"},
        {"name": "Agents & Coffee!", "date_iso": "2026-07-24T09:00", "resolved_url": "https://reddit.com/r/x/comments/aaa/y/"},
        {"name": "Brand New Event", "date_iso": "2026-07-25T18:00", "resolved_url": "https://lu.ma/brand-new"},
    ]
    existing_urls = {"https://lu.ma/ai-demo-night"}                      # cross-posted Luma event
    existing_title_dates = {(normalize_title("Agents & Coffee!"), "2026-07-24")}  # same title+date, diff URL
    kept = dedup_against_existing(extracted, existing_urls, existing_title_dates)
    assert [e["name"] for e in kept] == ["Brand New Event"]


def test_dedup_drops_intra_batch_duplicates():
    extracted = [
        {"name": "Same Event", "date_iso": "2026-07-23T18:00", "resolved_url": "https://lu.ma/same"},
        {"name": "Same Event", "date_iso": "2026-07-23T19:00", "resolved_url": "https://lu.ma/same"},
    ]
    kept = dedup_against_existing(extracted, set(), set())
    assert len(kept) == 1


# ── Availability + registration ──────────────────────────────────────────────

def test_is_available_true_on_200():
    with patch("app.connectors.reddit.httpx.get") as mock_get:
        mock_get.return_value.status_code = 200
        assert RedditConnector().is_available() is True


def test_is_available_false_when_unreachable():
    import httpx as _httpx
    with patch("app.connectors.reddit.httpx.get", side_effect=_httpx.ConnectError("down")):
        assert RedditConnector().is_available() is False


def test_registry_includes_reddit():
    from app.connectors.registry import CONNECTOR_REGISTRY
    assert CONNECTOR_REGISTRY.get("reddit") is RedditConnector


# ── Filter/resolve + end-to-end assembly (LLM + network mocked) ──────────────

def _extraction_response(events):
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps({"events": events})
    return mock_response


def test_filter_and_resolve_drops_past_undated_and_irrelevant():
    connector = RedditConnector()
    future = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%dT18:00")
    extracted = [
        {"name": "Good", "date_iso": future, "is_ai_relevant": True, "confidence": 0.8,
         "source_url": "https://lu.ma/good", "post_url": "https://reddit.com/r/x/comments/aaa/g/"},
        {"name": "Past", "date_iso": "2020-01-01T18:00", "is_ai_relevant": True, "confidence": 0.9,
         "source_url": None, "post_url": "https://reddit.com/r/x/comments/bbb/p/"},
        {"name": "Undated", "date_iso": None, "is_ai_relevant": True, "confidence": 0.5,
         "source_url": None, "post_url": "https://reddit.com/r/x/comments/ccc/u/"},
        {"name": "Hiking", "date_iso": future, "is_ai_relevant": False, "confidence": 0.9,
         "source_url": None, "post_url": "https://reddit.com/r/x/comments/ddd/h/"},
    ]
    kept = connector._filter_and_resolve(extracted, days_ahead=60)
    assert [e["name"] for e in kept] == ["Good"]
    assert kept[0]["resolved_url"] == "https://lu.ma/good"          # event link beats permalink
    assert kept[0]["start_dt_utc"].tzinfo is None                   # naive UTC convention


@pytest.mark.asyncio
async def test_fetch_events_end_to_end_mocked(db):
    """Retrieval + Groq mocked; verifies trim -> extract -> dedup -> RawEvent flow."""
    # Existing Luma event in DB — the cross-posted duplicate must be dropped
    db.add(Event(
        external_id="ai-demo-night", source="luma", title="AI Demo Night",
        url="https://lu.ma/ai-demo-night",
        start_datetime=datetime.utcnow() + timedelta(days=4),
    ))
    db.commit()

    future = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%dT18:00")
    connector = RedditConnector()

    candidates = [{
        "post_id": "abc123", "subreddit": "bayarea",
        "title": "AI Builders Demo Night", "selftext": "Come demo agents! https://lu.ma/new-event",
        "content_html": "",
        "permalink": "https://reddit.com/r/bayarea/comments/abc123/x/", "created_utc": 1750000000.0,
    }]
    llm_events = [
        {"name": "AI Builders Demo Night", "date_iso": future, "location": "Founders Space, SF",
         "organizer": "SF AI Builders", "is_ai_relevant": True, "confidence": 0.9,
         "source_url": "https://lu.ma/new-event",
         "post_url": "https://reddit.com/r/bayarea/comments/abc123/x/"},
        {"name": "AI Demo Night", "date_iso": future, "location": "SF",
         "organizer": None, "is_ai_relevant": True, "confidence": 0.8,
         "source_url": "https://lu.ma/ai-demo-night",   # already in DB via Luma
         "post_url": "https://reddit.com/r/bayarea/comments/zzz9/y/"},
    ]

    with patch.object(connector, "_retrieve_candidates", return_value=candidates), \
         patch.object(connector, "_scrape_luma_details", return_value={}), \
         patch("app.connectors.reddit.Groq") as MockGroq, \
         patch("app.database.SessionLocal") as MockSession:
        MockGroq.return_value.chat.completions.create.return_value = _extraction_response(llm_events)
        # _dedup_against_db opens its own session — point it at the test DB
        MockSession.return_value = db
        events = await connector.fetch_events()

    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, RawEvent)
    assert ev.source == "reddit"
    assert ev.title == "AI Builders Demo Night"
    assert ev.url == "https://lu.ma/new-event"
    assert "via-reddit" in ev.tags
    assert ev.external_id.startswith("r_")
