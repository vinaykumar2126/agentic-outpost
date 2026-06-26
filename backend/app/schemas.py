from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class EventSummary(BaseModel):
    id: int
    external_id: str
    source: str
    title: str
    short_description: Optional[str]
    url: str
    start_datetime: datetime
    end_datetime: Optional[datetime]
    location_name: Optional[str]
    location_address: Optional[str]
    is_online: bool
    organizer_name: Optional[str]
    tags: Optional[str]
    is_free: bool
    price_min: Optional[float]
    price_max: Optional[float]
    relevance_score: Optional[float]
    relevance_justification: Optional[str]

    model_config = {"from_attributes": True}


class EventDetail(EventSummary):
    description: Optional[str]
    ranked_at: Optional[datetime]
    fetched_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class EventListResponse(BaseModel):
    events: list[EventSummary]
    total: int
    limit: int
    offset: int


class ScrapeRunSchema(BaseModel):
    id: int
    source: str
    started_at: datetime
    completed_at: Optional[datetime]
    events_fetched: int
    events_new: int
    events_updated: int
    events_ranked: int
    status: str
    error_message: Optional[str]

    model_config = {"from_attributes": True}


class TriggerResponse(BaseModel):
    status: str
    sources: list[str]


class HealthResponse(BaseModel):
    status: str
    db: str
    scheduler: str
    next_run: Optional[str]
