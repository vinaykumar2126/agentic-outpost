from datetime import datetime, timedelta

from app.models import Event


def _make_event(db, external_id="evt1", source="luma", title="Test AI Event", score=8.0, days_from_now=7):
    event = Event(
        external_id=external_id,
        source=source,
        title=title,
        url=f"https://lu.ma/{external_id}",
        start_datetime=datetime.utcnow() + timedelta(days=days_from_now),
        relevance_score=score,
    )
    db.add(event)
    db.commit()
    return event


def test_list_events_returns_results(client, db):
    _make_event(db, external_id="e1")
    _make_event(db, external_id="e2", score=5.0)

    resp = client.get("/api/events")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["events"]) == 2


def test_list_events_min_score_filter(client, db):
    _make_event(db, external_id="high", score=9.0)
    _make_event(db, external_id="low", score=3.0)

    resp = client.get("/api/events?min_score=7")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["events"][0]["external_id"] == "high"


def test_list_events_sort_by_date(client, db):
    _make_event(db, external_id="later", days_from_now=14)
    _make_event(db, external_id="sooner", days_from_now=3)

    resp = client.get("/api/events?sort_by=date")
    assert resp.status_code == 200
    ids = [e["external_id"] for e in resp.json()["events"]]
    assert ids == ["sooner", "later"]


def test_get_event_not_found(client):
    resp = client.get("/api/events/99999")
    assert resp.status_code == 404


def test_get_event_returns_detail(client, db):
    event = _make_event(db)
    resp = client.get(f"/api/events/{event.id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == event.title


def test_health_endpoint(client):
    resp = client.get("/api/admin/health")
    assert resp.status_code == 200
    assert resp.json()["db"] == "ok"
