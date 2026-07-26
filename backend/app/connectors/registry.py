from app.connectors.base import EventConnector
from app.connectors.luma import LumaConnector
from app.connectors.aicamp import AicampConnector
from app.connectors.reddit import RedditConnector
# from app.connectors.eventbrite import EventbriteConnector  # Phase 2

# Order matters: reddit runs last so its cross-source dedup sees events that
# luma/aicamp inserted earlier in the same nightly run.
CONNECTOR_REGISTRY: dict[str, type[EventConnector]] = {
    "luma": LumaConnector,
    "aicamp": AicampConnector,
    "reddit": RedditConnector,
    # "eventbrite": EventbriteConnector,  # Phase 2
}


def get_active_connectors() -> list[EventConnector]:
    """Return instantiated connectors whose dependencies are available."""
    active = []
    for cls in CONNECTOR_REGISTRY.values():
        instance = cls()
        if instance.is_available():
            active.append(instance)
        else:
            import logging
            logging.getLogger(__name__).warning(
                "Connector %s is not available — skipping", cls.source_name
            )
    return active
