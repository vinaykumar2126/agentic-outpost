import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from groq import RateLimitError

from app.llm import chunk_by_chars, groq_json_chat


def _rate_limit_error(msg="Rate limit reached. Please try again in 2.5s."):
    resp = httpx.Response(429, request=httpx.Request("POST", "https://api.groq.com/x"),
                          json={"error": {"message": msg}})
    return RateLimitError(msg, response=resp, body={"error": {"message": msg}})


def test_chunk_by_chars_splits_and_keeps_all_items():
    items = [{"body": "x" * 4000}, {"body": "y" * 4000}, {"body": "z" * 4000}]
    batches = chunk_by_chars(items, char_budget=9000)
    assert len(batches) == 2
    assert sum(len(b) for b in batches) == 3


def test_chunk_by_chars_oversized_item_gets_own_batch():
    items = [{"body": "x" * 20000}, {"body": "small"}]
    batches = chunk_by_chars(items, char_budget=9000)
    assert len(batches) == 2
    assert len(batches[0]) == 1


def test_groq_json_chat_retries_on_rate_limit_then_succeeds():
    client = MagicMock()
    ok = MagicMock()
    ok.choices[0].message.content = json.dumps({"ok": True})
    client.chat.completions.create.side_effect = [_rate_limit_error(), ok]

    with patch("app.llm.time.sleep") as mock_sleep:
        content = groq_json_chat(client, model="m", messages=[])

    assert json.loads(content) == {"ok": True}
    assert client.chat.completions.create.call_count == 2
    # Honors the wait Groq suggested (2.5s + 1s margin)
    assert mock_sleep.call_args[0][0] == pytest.approx(3.5)


def test_groq_json_chat_raises_after_max_retries():
    client = MagicMock()
    client.chat.completions.create.side_effect = _rate_limit_error()
    with patch("app.llm.time.sleep"):
        with pytest.raises(RateLimitError):
            groq_json_chat(client, model="m", messages=[])
    assert client.chat.completions.create.call_count == 4  # initial + 3 retries
