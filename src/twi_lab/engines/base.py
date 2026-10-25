"""
Abstract base class for all translation engine adapters.

Every adapter (OPUS-MT, Khaya, future engines) must subclass EngineAdapter and
implement the three abstract members: engine_name, engine_version, and translate().

Design contract:
  - translate() MUST NOT raise on translation failure. Return a TranslationResult
    with status=FAILED and populate error_message / error_details instead.
  - translate() MUST record start_time and elapsed_time_ms.
  - translate() MUST NOT modify source_text.
  - The caller (runner) is responsible for persisting results; adapters only
    produce TranslationResult objects and log their own failures.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from twi_lab.schemas import TranslationResult


class EngineAdapter(ABC):
    """
    Abstract base for translation engine adapters.

    Subclasses implement translate() for a specific engine (OPUS-MT, Khaya, etc.)
    The runner calls translate() without knowing which engine is in use.
    """

    # ------------------------------------------------------------------
    # Identity properties (must be overridden)
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Short stable identifier used in result records (e.g. 'opus-mt', 'khaya')."""
        ...

    @property
    @abstractmethod
    def engine_version(self) -> Optional[str]:
        """Adapter version string (semver preferred, e.g. '0.1.0')."""
        ...

    # ------------------------------------------------------------------
    # Availability check (override in subclasses)
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        """
        Return True when the engine is ready to translate.

        Subclasses should check that required libraries are importable and
        any necessary config (API key, local model dir) is present.
        Default returns True; override to add real checks.
        """
        return True

    # ------------------------------------------------------------------
    # Translation interface (must be overridden)
    # ------------------------------------------------------------------

    @abstractmethod
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
        """
        Translate ``source_text`` and return a fully-populated TranslationResult.

        Implementations must:
          - Never raise; catch all exceptions and return status=FAILED.
          - Always set start_time (UTC) and elapsed_time_ms.
          - Never mutate source_text.
          - Populate engine_name, engine_version, model_identifier where applicable.

        Args:
            source_text:        The exact English passage to translate.
            experiment_id:      ID of the owning ExperimentRun.
            story_id:           Story the passage belongs to.
            passage_id:         Stable passage identifier.
            context_strategy:   Name of the context approach ('none', 'window_k', …).
            supplied_context:   Additional text passed alongside source_text.
            generation_settings: Engine-specific hyperparameters (beam size, temp, …).

        Returns:
            A TranslationResult. Status may be SUCCESS, FAILED, PARTIAL, or TIMEOUT.
        """
        ...

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"engine={self.engine_name!r}, "
            f"version={self.engine_version!r}, "
            f"available={self.is_available})"
        )
