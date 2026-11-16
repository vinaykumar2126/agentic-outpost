import json
from unittest.mock import MagicMock, patch

import pytest
from google.genai import errors

from app.llm import gemini_json_chat


def _api_error(code: int) -> errors.APIError:
    status = {429: "RESOURCE_EXHAUSTED", 400: "INVALID_ARGUMENT"}.get(code, "UNAVAILABLE")
    cls = errors.ClientError if code < 500 else errors.ServerError
    return cls(code, {"error": {"code": code, "message": "boom", "status": status}})


def _ok_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.text = json.dumps(payload)
    resp.usage_metadata = None
    return resp


def test_gemini_json_chat_retries_on_rate_limit_then_succeeds():
    client = MagicMock()
    client.models.generate_content.side_effect = [_api_error(429), _ok_response({"ok": True})]

    with patch("app.llm.time.sleep") as mock_sleep:
        content = gemini_json_chat(client, model="m", system="s", user="u")

    assert json.loads(content) == {"ok": True}
    assert client.models.generate_content.call_count == 2
    mock_sleep.assert_called_once()


def test_gemini_json_chat_requests_json_mode_with_system_prompt():
    client = MagicMock()
    client.models.generate_content.return_value = _ok_response({"ok": True})

    gemini_json_chat(client, model="m", system="be a ranker", user="u")

    config = client.models.generate_content.call_args.kwargs["config"]
    assert config.response_mime_type == "application/json"
    assert config.system_instruction == "be a ranker"


def test_gemini_json_chat_raises_after_max_retries():
    client = MagicMock()
    client.models.generate_content.side_effect = _api_error(503)
    with patch("app.llm.time.sleep"):
        with pytest.raises(errors.ServerError):
            gemini_json_chat(client, model="m", system="s", user="u")
    assert client.models.generate_content.call_count == 5  # initial + 4 retries


def test_gemini_json_chat_does_not_retry_client_errors():
    client = MagicMock()
    client.models.generate_content.side_effect = _api_error(400)
    with patch("app.llm.time.sleep") as mock_sleep:
        with pytest.raises(errors.ClientError):
            gemini_json_chat(client, model="m", system="s", user="u")
    assert client.models.generate_content.call_count == 1
    mock_sleep.assert_not_called()
