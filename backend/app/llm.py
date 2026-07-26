"""Shared Groq call helper with rate-limit awareness.

Groq's free tier enforces tokens-per-minute (TPM) per model. Two rules keep us
inside it: (1) callers chunk their payloads so no single request approaches the
budget, and (2) this helper retries 429s, honoring the wait Groq suggests in the
error message ("Please try again in 7.66s") instead of guessing.
"""

import logging
import re
import time

from groq import RateLimitError

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3


def groq_json_chat(client, *, model: str, messages: list[dict]) -> str:
    """One JSON-mode chat call with TPM-aware retry. Returns the raw content string."""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content
        except RateLimitError as exc:
            if attempt == _MAX_RETRIES:
                raise
            # Groq embeds the exact wait in the message; fall back to linear backoff
            m = re.search(r"try again in ([\d.]+)s", str(exc), re.IGNORECASE)
            wait = float(m.group(1)) + 1.0 if m else 20.0 * (attempt + 1)
            logger.info("Groq rate limit hit — sleeping %.1fs (attempt %d/%d)",
                        wait, attempt + 1, _MAX_RETRIES)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def chunk_by_chars(items: list[dict], char_budget: int) -> list[list[dict]]:
    """Split items into batches whose serialized size stays under char_budget.
    A single oversized item still gets its own batch rather than being dropped."""
    batches: list[list[dict]] = []
    current: list[dict] = []
    size = 0
    for item in items:
        item_size = len(str(item))
        if current and size + item_size > char_budget:
            batches.append(current)
            current = []
            size = 0
        current.append(item)
        size += item_size
    if current:
        batches.append(current)
    return batches
