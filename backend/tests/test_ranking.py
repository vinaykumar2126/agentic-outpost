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


def _mock_gemini_response(external_id: str, score: float):
    mock_response = MagicMock()
    mock_response.usage_metadata = None
    mock_response.text = json.dumps({
        "rankings": [
            {"external_id": external_id, "score": score, "justification": "Highly relevant."}
        ]
    })
    return mock_response


def test_rank_unscored_writes_score(db):
    event = _make_unscored_event(db)

    with patch("app.ranking.event_ranker.get_client") as MockClient:
        MockClient.return_value.models.generate_content.return_value = _mock_gemini_response(event.external_id, 9.0)
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

    with patch("app.ranking.event_ranker.get_client") as MockClient:
        ranker = EventRanker()
        count = ranker.rank_unscored(db)

    MockClient.return_value.models.generate_content.assert_not_called()
    assert count == 0


def test_rank_ignores_out_of_range_score(db):
    event = _make_unscored_event(db)

    with patch("app.ranking.event_ranker.get_client") as MockClient:
        MockClient.return_value.models.generate_content.return_value = _mock_gemini_response(event.external_id, 15.0)
        ranker = EventRanker()
        count = ranker.rank_unscored(db)

    db.refresh(event)
    assert count == 0
    assert event.relevance_score is None



def test_rank_skips_past_events(db):
    event = _make_unscored_event(db)
    event.start_datetime = datetime.utcnow() - timedelta(days=1)
    db.commit()

    with patch("app.ranking.event_ranker.get_client") as MockClient:
        ranker = EventRanker()
        count = ranker.rank_unscored(db)

    MockClient.return_value.models.generate_content.assert_not_called()
    assert count == 0


def test_rank_sends_full_description(db):
    event = _make_unscored_event(db)
    full = "Agenda: " + "multi-agent orchestration talk " * 30  # well past 400 chars
    event.description = full
    db.commit()

    with patch("app.ranking.event_ranker.get_client") as MockClient:
        generate = MockClient.return_value.models.generate_content
        generate.return_value = _mock_gemini_response(event.external_id, 8.0)
        EventRanker().rank_unscored(db)

    sent = generate.call_args.kwargs["contents"]
    assert full.strip() in sent

