"""Shared Gemini (Vertex AI) call helper.

All LLM calls go through gemini_json_chat: JSON-mode output, LangSmith token
accounting, and retry with exponential backoff on 429 / transient 5xx. Preview
models on Vertex (e.g. gemini-3-flash-preview) share dynamic quota, so short
bursts of "RESOURCE_EXHAUSTED" are expected and safe to retry.
"""

import logging
import time

from google import genai
from google.genai import errors, types
from langsmith import get_current_run_tree

from app.config import settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 4
_RETRYABLE_CODES = {429, 500, 503}
_BASE_BACKOFF_S = 5.0


def get_client() -> genai.Client:
    """Vertex AI client. Auth comes from Application Default Credentials
    (`gcloud auth application-default login` locally, the service account on Cloud Run)."""
    return genai.Client(
        vertexai=True,
        project=settings.google_cloud_project or None,
        location=settings.google_cloud_location,
    )


def gemini_json_chat(client: genai.Client, *, model: str, system: str, user: str) -> str:
    """One JSON-mode generate call with retry. Returns the raw JSON text."""
    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        # Gemini 3: Google recommends leaving temperature at its default (1.0);
        # low thinking keeps scoring/extraction fast and cheap.
        thinking_config=types.ThinkingConfig(thinking_level=settings.gemini_thinking_level),
    )
    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(model=model, contents=user, config=config)
            usage = response.usage_metadata
            if usage:
                run = get_current_run_tree()
                if run:
                    run.set(
                        usage_metadata={
                            "input_tokens": usage.prompt_token_count or 0,
                            "output_tokens": (usage.candidates_token_count or 0)
                            + (usage.thoughts_token_count or 0),
                            "total_tokens": usage.total_token_count or 0,
                        }
                    )
            if not response.text:
                raise ValueError(f"empty response (finish_reason={_finish_reason(response)})")
            return response.text
        except errors.APIError as exc:
            if exc.code not in _RETRYABLE_CODES or attempt == _MAX_RETRIES:
                raise
            wait = _BASE_BACKOFF_S * (2**attempt)
            logger.info("Gemini %s — sleeping %.0fs (attempt %d/%d)",
                        exc.code, wait, attempt + 1, _MAX_RETRIES)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def _finish_reason(response) -> str:
    try:
        return str(response.candidates[0].finish_reason)
    except (AttributeError, IndexError, TypeError):
        return "unknown"

