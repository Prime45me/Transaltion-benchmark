"""
Tests for the Khaya translation API adapter.

All HTTP calls are intercepted with unittest.mock — no network requests are
made, no API key is required, and no tokens are consumed.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from twi_lab.schemas import TranslationStatus


TRANSLATE_KWARGS = dict(
    experiment_id="exp-k01",
    story_id="STORY-K01",
    passage_id="STORY-K01-P01",
)

# ---------------------------------------------------------------------------
# Helper — build a mock requests.Response
# ---------------------------------------------------------------------------

def _mock_response(
    status_code: int = 200,
    body: dict | None = None,
    reason: str = "OK",
    raise_for_status: bool = False,
) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.reason = reason
    response.ok = (200 <= status_code < 300)
    response.json.return_value = body or {}
    response.text = json.dumps(body or {})
    if raise_for_status:
        response.raise_for_status.side_effect = Exception("HTTP error")
    return response


def _make_adapter(api_key: str = "test-key-abc", **kwargs):
    """Return a KhayaAdapter with a real or fake key, session mocked."""
    from twi_lab.engines.khaya import KhayaAdapter
    adapter = KhayaAdapter(
        api_key=api_key,
        base_url="https://api.khaya.ai/v1",
        timeout=10.0,
        **kwargs,
    )
    return adapter


# ---------------------------------------------------------------------------
# Identity and availability
# ---------------------------------------------------------------------------

class TestKhayaIdentity:

    def test_engine_name(self):
        adapter = _make_adapter()
        assert adapter.engine_name == "khaya"

    def test_engine_version_is_string(self):
        adapter = _make_adapter()
        assert isinstance(adapter.engine_version, str)

    def test_is_available_with_key_and_requests_installed(self):
        from twi_lab.engines.khaya import KhayaAdapter
        with patch.dict(__import__("sys").modules, {"requests": MagicMock()}):
            adapter = KhayaAdapter(api_key="sk-test")
            assert adapter.is_available is True

    def test_is_not_available_without_api_key(self):
        from twi_lab.engines.khaya import KhayaAdapter
        adapter = KhayaAdapter(api_key=None)
        # api_key is None → is_available must be False even if requests installed
        with patch.dict(__import__("sys").modules, {"requests": MagicMock()}):
            assert adapter.is_available is False

    def test_repr_contains_engine_name(self):
        adapter = _make_adapter()
        assert "khaya" in repr(adapter)


# ---------------------------------------------------------------------------
# Successful translation
# ---------------------------------------------------------------------------

class TestKhayaTranslateSuccess:

    def _run_success(self, response_body: dict, source: str = "The bird sang."):
        adapter = _make_adapter()
        mock_session = MagicMock()
        mock_session.post.return_value = _mock_response(200, response_body)
        adapter._session = mock_session

        return adapter.translate(source, **TRANSLATE_KWARGS), source

    def test_success_with_translation_key(self):
        result, source = self._run_success({"translation": "Ɔkɔ no anka."})
        assert result.status == TranslationStatus.SUCCESS
        assert result.translated_text == "Ɔkɔ no anka."

    def test_success_with_translated_text_key(self):
        result, _ = self._run_success({"translated_text": "Akyi na okoaa."})
        assert result.status == TranslationStatus.SUCCESS
        assert result.translated_text == "Akyi na okoaa."

    def test_success_with_text_key(self):
        result, _ = self._run_success({"text": "Translation here."})
        assert result.status == TranslationStatus.SUCCESS

    def test_success_with_plain_string_response(self):
        adapter = _make_adapter()
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.return_value = "Akwaaba ba yɛn sukuu mu."
        mock_session.post.return_value = mock_resp
        adapter._session = mock_session

        result = adapter.translate("Welcome to our school.", **TRANSLATE_KWARGS)
        assert result.status == TranslationStatus.SUCCESS
        assert result.translated_text == "Akwaaba ba yɛn sukuu mu."

    def test_source_text_unchanged(self):
        source = "Ama went home."
        result, _ = self._run_success({"translation": "Ama kɔɔ efie."}, source=source)
        assert result.source_text == source

    def test_engine_metadata_populated(self):
        result, _ = self._run_success({"translation": "Text."})
        assert result.engine_name == "khaya"
        assert result.engine_version is not None

    def test_passage_ids_correct(self):
        result, _ = self._run_success({"translation": "Ok."})
        assert result.experiment_id == "exp-k01"
        assert result.story_id == "STORY-K01"
        assert result.passage_id == "STORY-K01-P01"

    def test_elapsed_time_recorded(self):
        result, _ = self._run_success({"translation": "Ok."})
        assert result.elapsed_time_ms is not None
        assert result.elapsed_time_ms >= 0

    def test_source_char_count_auto_filled(self):
        source = "The drum sounded."
        result, _ = self._run_success({"translation": "Ok."}, source=source)
        assert result.source_character_count == len(source)


# ---------------------------------------------------------------------------
# Missing API key
# ---------------------------------------------------------------------------

class TestKhayaMissingApiKey:

    def test_missing_key_returns_failed_immediately(self):
        from twi_lab.engines.khaya import KhayaAdapter
        adapter = KhayaAdapter(api_key=None)
        result = adapter.translate("Hello.", **TRANSLATE_KWARGS)

        assert result.status == TranslationStatus.FAILED
        assert "KHAYA_API_KEY" in result.error_message
        assert result.error_details["reason"] == "missing_api_key"

    def test_missing_key_does_not_call_network(self):
        from twi_lab.engines.khaya import KhayaAdapter
        adapter = KhayaAdapter(api_key=None)
        mock_session = MagicMock()
        adapter._session = mock_session

        adapter.translate("Hello.", **TRANSLATE_KWARGS)
        mock_session.post.assert_not_called()


# ---------------------------------------------------------------------------
# HTTP error responses
# ---------------------------------------------------------------------------

class TestKhayaHTTPErrors:

    def _run_with_http_error(self, status_code: int, body: dict | None = None):
        adapter = _make_adapter()
        mock_session = MagicMock()
        mock_session.post.return_value = _mock_response(
            status_code, body or {"detail": "error"}, reason="Error"
        )
        adapter._session = mock_session
        return adapter.translate("Hello.", **TRANSLATE_KWARGS)

    def test_401_returns_failed(self):
        result = self._run_with_http_error(401)
        assert result.status == TranslationStatus.FAILED
        assert "401" in result.error_message

    def test_429_returns_failed(self):
        result = self._run_with_http_error(429)
        assert result.status == TranslationStatus.FAILED
        assert result.error_details["http_status"] == 429

    def test_500_returns_failed(self):
        result = self._run_with_http_error(500)
        assert result.status == TranslationStatus.FAILED

    def test_http_error_never_raises(self):
        """HTTP error must not propagate as an exception."""
        adapter = _make_adapter()
        mock_session = MagicMock()
        mock_session.post.return_value = _mock_response(503, reason="Service Unavailable")
        adapter._session = mock_session

        result = adapter.translate("Hello.", **TRANSLATE_KWARGS)
        assert result is not None  # must return, not raise


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------

class TestKhayaTimeout:

    def test_timeout_returns_timeout_status(self):
        import requests

        adapter = _make_adapter()
        mock_session = MagicMock()
        mock_session.post.side_effect = requests.exceptions.Timeout("timed out")
        adapter._session = mock_session

        result = adapter.translate("Hello.", **TRANSLATE_KWARGS)
        assert result.status == TranslationStatus.TIMEOUT
        assert "timed out" in result.error_message.lower() or "timeout" in result.error_message.lower()
        assert result.error_details["timeout_seconds"] == 10.0

    def test_timeout_never_raises(self):
        import requests

        adapter = _make_adapter()
        mock_session = MagicMock()
        mock_session.post.side_effect = requests.exceptions.Timeout()
        adapter._session = mock_session

        result = adapter.translate("Hello.", **TRANSLATE_KWARGS)
        assert result is not None


# ---------------------------------------------------------------------------
# Empty / partial response
# ---------------------------------------------------------------------------

class TestKhayaPartialResponse:

    def test_empty_translation_key_returns_partial(self):
        adapter = _make_adapter()
        mock_session = MagicMock()
        mock_session.post.return_value = _mock_response(200, {"status": "ok"})
        adapter._session = mock_session

        result = adapter.translate("Hello.", **TRANSLATE_KWARGS)
        assert result.status == TranslationStatus.PARTIAL
        assert result.translated_text is None

    def test_partial_includes_response_keys_in_details(self):
        adapter = _make_adapter()
        mock_session = MagicMock()
        mock_session.post.return_value = _mock_response(200, {"message": "queued"})
        adapter._session = mock_session

        result = adapter.translate("Hello.", **TRANSLATE_KWARGS)
        assert "response_keys" in result.error_details


# ---------------------------------------------------------------------------
# Connection error (non-timeout network failure)
# ---------------------------------------------------------------------------

class TestKhayaConnectionError:

    def test_connection_error_returns_failed(self):
        import requests

        adapter = _make_adapter()
        mock_session = MagicMock()
        mock_session.post.side_effect = requests.exceptions.ConnectionError("refused")
        adapter._session = mock_session

        result = adapter.translate("Hello.", **TRANSLATE_KWARGS)
        assert result.status == TranslationStatus.FAILED
        assert result.error_message is not None

    def test_connection_error_never_raises(self):
        import requests

        adapter = _make_adapter()
        mock_session = MagicMock()
        mock_session.post.side_effect = requests.exceptions.ConnectionError()
        adapter._session = mock_session

        result = adapter.translate("Hello.", **TRANSLATE_KWARGS)
        assert result is not None


# ---------------------------------------------------------------------------
# Context strategy recorded correctly
# ---------------------------------------------------------------------------

class TestKhayaContextStrategy:

    def test_context_strategy_recorded_in_result(self):
        adapter = _make_adapter()
        mock_session = MagicMock()
        mock_session.post.return_value = _mock_response(200, {"translation": "Ok."})
        adapter._session = mock_session

        result = adapter.translate(
            "Hello.",
            **TRANSLATE_KWARGS,
            context_strategy="window_k",
            supplied_context="Previous sentence.",
        )
        assert result.context_strategy == "window_k"
        assert result.supplied_context == "Previous sentence."


# ---------------------------------------------------------------------------
# API Key Failover and Optimization Tests
# ---------------------------------------------------------------------------

class TestKhayaOptimization:

    def test_cache_hit_avoids_repeated_network_call(self):
        adapter = _make_adapter()
        mock_session = MagicMock()
        mock_session.post.return_value = _mock_response(200, {"translation": "Efie."})
        adapter._session = mock_session

        res1 = adapter.translate("Home.", **TRANSLATE_KWARGS)
        assert res1.status == TranslationStatus.SUCCESS
        assert res1.translated_text == "Efie."
        assert mock_session.post.call_count == 1

        # Second call with same text should hit cache
        res2 = adapter.translate("Home.", **TRANSLATE_KWARGS)
        assert res2.status == TranslationStatus.SUCCESS
        assert res2.translated_text == "Efie."
        assert res2.generation_settings.get("cached") is True
        assert mock_session.post.call_count == 1  # Not called again!

    def test_failover_to_secondary_key_on_429(self):
        from twi_lab.engines.khaya import KhayaAdapter
        adapter = KhayaAdapter(
            api_key="primary-key-123",
            secondary_api_key="secondary-key-456",
            base_url="https://api.khaya.ai/v1",
        )

        resp_429 = _mock_response(429, {"detail": "Rate limit exceeded"})
        resp_200 = _mock_response(200, {"translation": "Akwaaba"})

        mock_session_primary = MagicMock()
        mock_session_primary.post.return_value = resp_429

        mock_session_sec = MagicMock()
        mock_session_sec.post.return_value = resp_200

        with patch.object(adapter, "_get_session", side_effect=[mock_session_primary, mock_session_sec]):
            result = adapter.translate("Welcome.", **TRANSLATE_KWARGS)

        assert result.status == TranslationStatus.SUCCESS
        assert result.translated_text == "Akwaaba"
