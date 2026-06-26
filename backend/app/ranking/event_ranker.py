import json
import logging
from datetime import datetime, timezone

import ollama
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Event

logger = logging.getLogger(__name__)

BATCH_SIZE = 20

SYSTEM_PROMPT = """You are an AI event relevance ranker. You help an early-career software engineer
targeting AI Engineer roles discover the most valuable Bay Area AI events for networking and career growth.

Score each event from 0 to 10 using this rubric:

0–2: Not relevant. General tech meetup, non-AI topic, or unrelated field.
3–4: Loosely AI-related. Broad data science, analytics, or AI-adjacent content with no engineering depth.
5–6: Moderately relevant. AI/ML engineering content but not specifically focused on production systems or agentic workflows.
7–8: Highly relevant. Focuses on LLM engineering, AI infrastructure, production AI deployment, or agent frameworks
     (LangChain, LlamaIndex, AutoGen, CrewAI, etc.).
9–10: Extremely relevant. Directly covers agentic AI workflows, multi-agent systems in production, AI engineering
      career development, or hands-on agentic AI building sessions.

Add 0.5–1.0 to the score if the event explicitly enables 1:1 networking with AI engineers or hiring managers.
Cap the final score at 10.0.

Return ONLY a JSON array — no explanation, no markdown fences."""

RANKING_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "external_id": {"type": "string"},
            "score": {"type": "number"},
            "justification": {"type": "string"},
        },
        "required": ["external_id", "score", "justification"],
    },
}


class EventRanker:
    def __init__(self):
        self.client = ollama.Client(host=settings.ollama_base_url)

    def rank_unscored(self, db: Session) -> int:
        """Score all events with relevance_score IS NULL. Returns number of events ranked."""
        unscored = db.query(Event).filter(Event.relevance_score.is_(None)).all()
        if not unscored:
            logger.info("No unscored events found")
            return 0

        ranked_count = 0
        for i in range(0, len(unscored), BATCH_SIZE):
            batch = unscored[i : i + BATCH_SIZE]
            try:
                results = self._rank_batch(batch)
                for item in results:
                    event = next((e for e in batch if e.external_id == item["external_id"]), None)
                    if event is None:
                        continue
                    score = float(item["score"])
                    if not (0.0 <= score <= 10.0):
                        logger.warning("Score out of range for %s: %s", event.external_id, score)
                        continue
                    event.relevance_score = round(score, 1)
                    event.relevance_justification = str(item.get("justification", ""))[:300]
                    event.ranked_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    ranked_count += 1
                db.commit()
            except Exception as exc:
                logger.error("Ranking batch failed: %s", exc)
                db.rollback()

        logger.info("Ranked %d events", ranked_count)
        return ranked_count

    def _rank_batch(self, events: list[Event]) -> list[dict]:
        payload = [
            {
                "external_id": e.external_id,
                "title": e.title,
                "description": (e.short_description or "")[:400],
                "organizer": e.organizer_name or "",
                "tags": json.loads(e.tags) if e.tags else [],
            }
            for e in events
        ]

        user_prompt = (
            f"Rank the following {len(events)} events. "
            "Each justification must be plain text, max 20 words.\n\n"
            f"Events:\n{json.dumps(payload, indent=2)}"
        )

        response = self.client.chat(
            model=settings.ollama_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            format=RANKING_SCHEMA,
        )

        return json.loads(response.message.content)
