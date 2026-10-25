"""
Khaya translation API adapter.

Translates English text to Asante Twi using the Khaya cloud REST API.

Requirements:
    pip install requests>=2.31.0   (already in Phase 2 deps)
    KHAYA_API_KEY set in .env or environment

Network dependency: YES — this adapter requires internet access and a valid
API key. It cannot function offline. Set KHAYA_API_KEY=your_key_here in .env.

The adapter is designed for resilience:
  - All HTTP errors return a FAILED TranslationResult, never raise.
  - Timeouts return status=TIMEOUT so they can be counted separately.
  - Missing API key returns FAILED immediately without making any network call.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from twi_lab.config import get_settings
from twi_lab.context import format_engine_input
from twi_lab.engines.base import EngineAdapter
from twi_lab.logging_config import setup_logging
from twi_lab.schemas import TranslationResult, TranslationStatus

logger = setup_logging()

_ADAPTER_VERSION = "0.1.0"

# Language codes used in the Khaya API payload.
# Update if Khaya changes its language identifier scheme.
_SOURCE_LANG = "en"
_TARGET_LANG = "tw"  # Asante Twi language code for the Khaya API


_UNSET = object()


class KhayaAdapter(EngineAdapter):
    """
    Khaya API English → Asante Twi adapter.

    Uses a persistent requests.Session for connection reuse across multiple
    translate() calls within the same experiment run.

    Attributes:
        api_key:   Khaya API authentication token.
        base_url:  Root URL of the Khaya translation API.
        timeout:   Per-request HTTP timeout in seconds.
    """

    def __init__(
        self,
        api_key: Optional[str] = _UNSET,  # type: ignore[assignment]
        secondary_api_key: Optional[str] = _UNSET,  # type: ignore[assignment]
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        enable_cache: bool = True,
    ) -> None:
        settings = get_settings()
        if api_key is _UNSET:
            self._api_key = settings.khaya_api_key
            self._secondary_api_key = (
                secondary_api_key
                if secondary_api_key is not _UNSET
                else settings.khaya_api_secondary_key
            )
        else:
            self._api_key = api_key
            self._secondary_api_key = (
                secondary_api_key if secondary_api_key is not _UNSET else None
            )

        self._base_url: str = (base_url or settings.khaya_api_base_url).rstrip("/")
        self._timeout: float = float(timeout or settings.khaya_timeout_seconds)
        self._enable_cache: bool = enable_cache
        self._cache: dict[str, str] = {}
        self._session = None  # Lazy session creation

    # ------------------------------------------------------------------
    # EngineAdapter identity
    # ------------------------------------------------------------------

    @property
    def engine_name(self) -> str:
        return "khaya"

    @property
    def engine_version(self) -> Optional[str]:
        return _ADAPTER_VERSION

    @property
    def is_available(self) -> bool:
        """True when requests is installed and at least one API key is present."""
        try:
            import requests  # noqa: F401
        except ImportError:
            return False
        return bool(self._api_key or self._secondary_api_key)

    # ------------------------------------------------------------------
    # Internal: lazy session creation
    # ------------------------------------------------------------------

    def _get_session(self, api_key: Optional[str] = None):
        """Return a requests.Session with auth headers pre-set."""
        if self._session is not None and api_key is None:
            return self._session

        try:
            import requests
        except ImportError as exc:
            raise RuntimeError(
                "The 'requests' package is required for the Khaya adapter.\n"
                "  pip install requests"
            ) from exc

        key = api_key or self._api_key
        session = requests.Session()
        session.headers.update(
            {
                "Ocp-Apim-Subscription-Key": key or "",
                "Authorization": f"Token {key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Cache-Control": "no-cache",
            }
        )
        if api_key is None:
            self._session = session
        return session

    # ------------------------------------------------------------------
    # EngineAdapter.translate
    # ------------------------------------------------------------------

    def translate(
        self,
        source_text: str,
        *,
        experiment_id: str,
        story_id: str,
        passage_id: str,
        context_strategy: str = "none",
        supplied_context: Optional[str] = None,
        generation_settings: Optional[dict] = None,
    ) -> TranslationResult:
        """Translate source_text via the Khaya REST API. Never raises."""
        start_time = datetime.now(timezone.utc)
        t0 = time.monotonic()
        gen = generation_settings or {}

        # --- In-memory cache check (optimizes API quota) ---
        cache_lookup_key = (source_text, context_strategy, str(supplied_context or ""))
        if self._enable_cache and cache_lookup_key in self._cache:
            cached_text = self._cache[cache_lookup_key]
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            logger.debug("Khaya: cache hit for passage %s.", passage_id)
            return TranslationResult(
                experiment_id=experiment_id,
                story_id=story_id,
                passage_id=passage_id,
                engine_name=self.engine_name,
                engine_version=self.engine_version,
                context_strategy=context_strategy,
                source_text=source_text,
                supplied_context=supplied_context,
                translated_text=cached_text,
                start_time=start_time,
                elapsed_time_ms=elapsed_ms,
                status=TranslationStatus.SUCCESS,
                generation_settings={**gen, "cached": True},
            )

        active_key = self._api_key or self._secondary_api_key

        # --- Guard: no API key ---
        if not active_key:
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            logger.error(
                "Khaya: KHAYA_API_KEY not set — skipping passage %s.", passage_id
            )
            return TranslationResult(
                experiment_id=experiment_id,
                story_id=story_id,
                passage_id=passage_id,
                engine_name=self.engine_name,
                engine_version=self.engine_version,
                context_strategy=context_strategy,
                source_text=source_text,
                supplied_context=supplied_context,
                start_time=start_time,
                elapsed_time_ms=elapsed_ms,
                status=TranslationStatus.FAILED,
                error_message="KHAYA_API_KEY is not configured.",
                error_details={"reason": "missing_api_key"},
                generation_settings=gen,
            )

        # --- Main translation call ---
        try:
            import requests

            session = self._get_session()
            input_text = format_engine_input(source_text, supplied_context, context_strategy)
            payload = {
                "in": input_text,
                "lang": f"{_SOURCE_LANG}-{_TARGET_LANG}",
                "text": input_text,
                "source_language": _SOURCE_LANG,
                "target_language": _TARGET_LANG,
            }

            response = session.post(
                f"{self._base_url}/translate",
                json=payload,
                timeout=self._timeout,
            )

            # --- Key failover: if rate limited or unauthorized and secondary key exists ---
            if (
                not response.ok
                and response.status_code in (401, 403, 429)
                and self._secondary_api_key
                and active_key != self._secondary_api_key
            ):
                logger.warning(
                    "Khaya: key returned HTTP %d for passage %s. Failing over to secondary API key.",
                    response.status_code, passage_id,
                )
                sec_session = self._get_session(self._secondary_api_key)
                response = sec_session.post(
                    f"{self._base_url}/translate",
                    json=payload,
                    timeout=self._timeout,
                )

            elapsed_ms = (time.monotonic() - t0) * 1000.0

            # --- HTTP error ---
            if not response.ok:
                error_body: dict = {}
                try:
                    error_body = response.json()
                except Exception:
                    error_body = {"raw": response.text[:300]}

                logger.error(
                    "Khaya: HTTP %d for passage %s — %s",
                    response.status_code, passage_id, error_body,
                )

                error_category = "unknown_http_error"
                if response.status_code in (401, 403):
                    error_category = "authentication_error"
                elif response.status_code == 429:
                    error_category = "quota_or_rate_limit"
                elif response.status_code == 400:
                    error_category = "invalid_payload"
                elif response.status_code >= 500:
                    error_category = "server_error"

                return TranslationResult(
                    experiment_id=experiment_id,
                    story_id=story_id,
                    passage_id=passage_id,
                    engine_name=self.engine_name,
                    engine_version=self.engine_version,
                    context_strategy=context_strategy,
                    source_text=source_text,
                    supplied_context=supplied_context,
                    start_time=start_time,
                    elapsed_time_ms=elapsed_ms,
                    status=TranslationStatus.FAILED,
                    error_message=f"HTTP {response.status_code}: {response.reason}",
                    error_details={
                        "http_status": response.status_code,
                        "error_category": error_category,
                        "body": error_body,
                    },
                    generation_settings=gen,
                )

            # --- Parse response ---
            data = response.json()
            translated_text: Optional[str] = None

            if isinstance(data, str):
                translated_text = data.strip()
            elif isinstance(data, dict):
                translated_text = (
                    data.get("translation")
                    or data.get("translated_text")
                    or data.get("text")
                    or data.get("out")
                )

            if not translated_text:
                resp_keys = list(data.keys()) if isinstance(data, dict) else [str(type(data))]
                logger.warning(
                    "Khaya: success HTTP status but no translation text for passage %s. "
                    "Response details: %s",
                    passage_id, resp_keys,
                )
                return TranslationResult(
                    experiment_id=experiment_id,
                    story_id=story_id,
                    passage_id=passage_id,
                    engine_name=self.engine_name,
                    engine_version=self.engine_version,
                    context_strategy=context_strategy,
                    source_text=source_text,
                    supplied_context=supplied_context,
                    start_time=start_time,
                    elapsed_time_ms=elapsed_ms,
                    status=TranslationStatus.PARTIAL,
                    error_message="API returned HTTP 200 but no translation text.",
                    error_details={"response_keys": resp_keys},
                    generation_settings=gen,
                )

            if self._enable_cache and translated_text:
                self._cache[cache_lookup_key] = translated_text

            logger.debug(
                "Khaya: passage %s translated in %.1f ms.", passage_id, elapsed_ms
            )
            return TranslationResult(
                experiment_id=experiment_id,
                story_id=story_id,
                passage_id=passage_id,
                engine_name=self.engine_name,
                engine_version=self.engine_version,
                context_strategy=context_strategy,
                source_text=source_text,
                supplied_context=supplied_context,
                translated_text=translated_text,
                start_time=start_time,
                elapsed_time_ms=elapsed_ms,
                status=TranslationStatus.SUCCESS,
                generation_settings=gen,
            )

        except Exception as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            exc_type = type(exc).__name__

            # Classify timeout vs other failures
            is_timeout = "Timeout" in exc_type or "timeout" in exc_type.lower()
            try:
                import requests as _req
                is_timeout = is_timeout or isinstance(exc, _req.exceptions.Timeout)
            except ImportError:
                pass

            if is_timeout:
                logger.error(
                    "Khaya: request timed out after %.1fs for passage %s.",
                    self._timeout, passage_id,
                )
                return TranslationResult(
                    experiment_id=experiment_id,
                    story_id=story_id,
                    passage_id=passage_id,
                    engine_name=self.engine_name,
                    engine_version=self.engine_version,
                    context_strategy=context_strategy,
                    source_text=source_text,
                    supplied_context=supplied_context,
                    start_time=start_time,
                    elapsed_time_ms=elapsed_ms,
                    status=TranslationStatus.TIMEOUT,
                    error_message=f"Request timed out after {self._timeout}s.",
                    error_details={
                        "timeout_seconds": self._timeout,
                        "exception_type": exc_type,
                    },
                    generation_settings=gen,
                )

            logger.error(
                "Khaya: unexpected error for passage %s: %s", passage_id, exc
            )
            return TranslationResult(
                experiment_id=experiment_id,
                story_id=story_id,
                passage_id=passage_id,
                engine_name=self.engine_name,
                engine_version=self.engine_version,
                context_strategy=context_strategy,
                source_text=source_text,
                supplied_context=supplied_context,
                start_time=start_time,
                elapsed_time_ms=elapsed_ms,
                status=TranslationStatus.FAILED,
                error_message=str(exc),
                error_details={"exception_type": exc_type},
                generation_settings=gen,
            )
