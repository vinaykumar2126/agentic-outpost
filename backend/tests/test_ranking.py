import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.models import Event
from app.ranking.event_ranker import EventRanker


def _make_unscored_event(db, external_id="evt1"):
    event = Event(
        external_id=external_id,
        source="luma",
        title="Agentic AI in Production",
        short_description="Deep dive into multi-agent systems running at scale.",
        url=f"https://lu.ma/{external_id}",
        start_datetime=datetime.utcnow() + timedelta(days=7),
    )
    db.add(event)
    db.commit()
    return event


def _mock_ollama_response(external_id: str, score: float):
    mock_response = MagicMock()
    mock_response.message.content = json.dumps([
        {"external_id": external_id, "score": score, "justification": "Highly relevant."}
    ])
    return mock_response


def test_rank_unscored_writes_score(db):
    event = _make_unscored_event(db)

    with patch("app.ranking.event_ranker.ollama.Client") as MockClient:
        MockClient.return_value.chat.return_value = _mock_ollama_response(event.external_id, 9.0)
        ranker = EventRanker()
        count = ranker.rank_unscored(db)

    db.refresh(event)
    assert count == 1
    assert event.relevance_score == 9.0
    assert event.ranked_at is not None


def test_rank_skips_already_scored(db):
    event = _make_unscored_event(db)
    event.relevance_score = 7.0
    db.commit()

    with patch("app.ranking.event_ranker.ollama.Client") as MockClient:
        ranker = EventRanker()
        count = ranker.rank_unscored(db)

    MockClient.return_value.chat.assert_not_called()
    assert count == 0


def test_rank_ignores_out_of_range_score(db):
    event = _make_unscored_event(db)

    with patch("app.ranking.event_ranker.ollama.Client") as MockClient:
        MockClient.return_value.chat.return_value = _mock_ollama_response(event.external_id, 15.0)
        ranker = EventRanker()
        count = ranker.rank_unscored(db)

    db.refresh(event)
    assert count == 0
    assert event.relevance_score is None

