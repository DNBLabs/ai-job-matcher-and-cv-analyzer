"""Unit tests for the OpenAI LlmClient adapter error handling."""

from unittest.mock import MagicMock

import httpx
import pytest
from openai import APIError

from app.adapters.openai_client import OpenAiLlmClient
from app.ports.llm_client import LlmClientError


def _client_with_parse(parse: MagicMock) -> OpenAiLlmClient:
    """Build an adapter whose underlying OpenAI chat parse call is mocked."""
    client = OpenAiLlmClient(
        api_key="sk-test-key",
        title_model="gpt-4o-mini",
        scoring_model="gpt-4o",
    )
    client._client.chat.completions.parse = parse  # type: ignore[attr-defined]
    return client


def test_suggest_job_titles_preserves_api_error_detail() -> None:
    """A provider APIError surfaces its type and message in the LlmClientError chain.

    Issue #52: ``raise LlmClientError("OpenAI API request failed")`` discarded the
    concrete provider failure (e.g. an auth error from an invalid prod key), leaving
    the masked 502 undiagnosable. The wrapped error must carry actionable detail.
    """
    api_error = APIError(
        "Incorrect API key provided: sk-***redacted",
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
        body=None,
    )
    parse = MagicMock(side_effect=api_error)
    client = _client_with_parse(parse)

    with pytest.raises(LlmClientError) as exc_info:
        client.suggest_job_titles(cv_text="Senior backend engineer.")

    message = str(exc_info.value)
    assert "APIError" in message
    assert "Incorrect API key provided" in message
    # Original provider error is preserved as the cause for full server-side context.
    assert exc_info.value.__cause__ is api_error
