from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Event
from app.schemas import EventDetail, EventListResponse, EventSummary

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=EventListResponse)
def list_events(
    min_score: float = Query(0.0, ge=0, le=10),
    max_score: float = Query(10.0, ge=0, le=10),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    source: Optional[str] = Query(None),
    is_free: Optional[bool] = Query(None),
    is_online: Optional[bool] = Query(None),
    q: Optional[str] = Query(None),
    sort_by: str = Query("score", pattern="^(score|date)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    today = datetime.now(timezone.utc).replace(tzinfo=None).replace(hour=0, minute=0, second=0, microsecond=0)
    # Default to today so the feed only shows upcoming events unless the caller explicitly requests history
    query = db.query(Event).filter(Event.start_datetime >= (date_from or today))

    if date_to:
        query = query.filter(Event.start_datetime <= datetime.combine(date_to, datetime.max.time()))
    if source:
        query = query.filter(Event.source == source)
    if is_free is not None:
        query = query.filter(Event.is_free == is_free)
    if is_online is not None:
        query = query.filter(Event.is_online == is_online)
    if q:
        like = f"%{q}%"
        query = query.filter(
            Event.title.ilike(like) | Event.short_description.ilike(like)
        )
    if min_score > 0 or max_score < 10:
        query = query.filter(
            Event.relevance_score >= min_score, Event.relevance_score <= max_score
        )

    total = query.count()

    if sort_by == "score":
        # nulls_last keeps unranked events below scored ones rather than floating to the top
        query = query.order_by(Event.relevance_score.desc().nulls_last(), Event.start_datetime.asc())
    else:
        query = query.order_by(Event.start_datetime.asc())

    events = query.offset(offset).limit(limit).all()
    return EventListResponse(
        events=[EventSummary.model_validate(e) for e in events],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{event_id}", response_model=EventDetail)
def get_event(event_id: int, db: Session = Depends(get_db)):
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return EventDetail.model_validate(event)
