from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class RawEvent:
    external_id: str
    source: str
    title: str
    description: str
    url: str
    start_datetime: datetime  # UTC
    end_datetime: Optional[datetime] = None
    location_name: Optional[str] = None
    location_address: Optional[str] = None
    is_online: bool = False
    organizer_name: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    is_free: bool = True
    price_min: Optional[float] = None
    price_max: Optional[float] = None


class EventConnector(ABC):
    source_name: str  # set as class attribute in each subclass

    @abstractmethod
    async def fetch_events(self, days_ahead: int = 60) -> List[RawEvent]:
        """
        Fetch upcoming AI-relevant events in the Bay Area.
        Must be idempotent — safe to call repeatedly.
        Returns events in any order; deduplication is handled upstream.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """
        Return True if all required credentials/dependencies are present.
        Called at startup to skip unconfigured connectors gracefully.
        """
        ...
