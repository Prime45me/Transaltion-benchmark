"""
OPUS-MT local translation adapter.

Uses the Helsinki-NLP/opus-mt-en-tw MarianMT model for offline
English → Asante Twi inference via HuggingFace Transformers.

Model weights are NOT downloaded automatically. Download explicitly with:

    python -m twi_lab.engines.opus_mt --download

Requirements (install separately — not in Phase 1 base deps):
    pip install transformers>=4.40.0 sentencepiece>=0.1.99

The adapter uses lazy imports: transformers is only imported when translate()
or download_model() is called, so importing this module does not require
transformers to be installed.

Network dependency: NONE once the model is downloaded.
GPU dependency: NONE — CPU inference is the default and is assumed.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from twi_lab.config import get_settings
from twi_lab.context import format_engine_input
from twi_lab.engines.base import EngineAdapter
from twi_lab.logging_config import setup_logging
from twi_lab.schemas import TranslationResult, TranslationStatus

logger = setup_logging()

_ADAPTER_VERSION = "0.1.0"


class OPUSMTAdapter(EngineAdapter):
    """
    Local OPUS-MT English → Asante Twi adapter using MarianMT.

    The model and tokenizer are loaded lazily on the first translate() call.
    Subsequent calls reuse the in-memory model (no repeated disk I/O).

    Attributes:
        model_name:  HuggingFace model ID (default: Helsinki-NLP/opus-mt-en-tw).
        model_dir:   Local directory containing downloaded model weights.
        device:      Compute device ('cpu' — GPU not assumed in Phase 2).
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        model_dir: Optional[Path] = None,
        device: Optional[str] = None,
    ) -> None:
        settings = get_settings()
        self._model_name: str = model_name or settings.opus_mt_model_name
        self._model_dir: Path = Path(
            model_dir or settings.resolve_path(settings.opus_mt_model_dir)
        )
        self._device: str = device or settings.local_device
        # Lazy-loaded on first translate call
        self._model = None
        self._tokenizer = None

    # ------------------------------------------------------------------
    # EngineAdapter identity
    # ------------------------------------------------------------------

    @property
    def engine_name(self) -> str:
        return "opus-mt"

    @property
    def engine_version(self) -> Optional[str]:
        return _ADAPTER_VERSION

    @property
    def is_available(self) -> bool:
        """True when transformers is importable AND model weights exist locally."""
        try:
            import transformers  # noqa: F401
        except ImportError:
            return False
        return self._model_dir.exists()

    # ------------------------------------------------------------------
    # Internal: lazy model loading
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        """Load tokenizer and model from disk on first call. No-op thereafter."""
        if self._model is not None:
            return

        try:
            from transformers import MarianMTModel, MarianTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "The 'transformers' and 'sentencepiece' packages are required for "
                "OPUS-MT inference.\n"
                "  pip install transformers sentencepiece"
            ) from exc

        if not self._model_dir.exists():
            raise RuntimeError(
                f"OPUS-MT model weights not found at: {self._model_dir}\n"
                "Download the model first:\n"
                "  python -m twi_lab.engines.opus_mt --download"
            )

        logger.info("Loading OPUS-MT model from %s", self._model_dir)
        try:
            self._tokenizer = MarianTokenizer.from_pretrained(str(self._model_dir))
            self._model = MarianMTModel.from_pretrained(str(self._model_dir))
            self._model.eval()
            logger.info("OPUS-MT model loaded (device=%s).", self._device)
        except Exception as exc:
            self._model = None
            self._tokenizer = None
            raise RuntimeError(f"Failed to load OPUS-MT model: {exc}") from exc

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
        """Translate using the local OPUS-MT model. Never raises."""
        start_time = datetime.now(timezone.utc)
        t0 = time.monotonic()
        gen = generation_settings or {}

        try:
            self._load_model()

            input_text = format_engine_input(source_text, supplied_context, context_strategy)
            inputs = self._tokenizer(
                [input_text],
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=gen.get("max_source_length", 512),
            )

            import torch  # noqa: PLC0415 — inside try; torch is a transformers dep

            with torch.no_grad():
                output_ids = self._model.generate(
                    **inputs,
                    num_beams=gen.get("num_beams", 4),
                    max_length=gen.get("max_length", 512),
                    early_stopping=gen.get("early_stopping", True),
                )

            translated_text: str = self._tokenizer.decode(
                output_ids[0], skip_special_tokens=True
            )
            elapsed_ms = (time.monotonic() - t0) * 1000.0

            logger.debug(
                "OPUS-MT: passage %s translated in %.1f ms.", passage_id, elapsed_ms
            )
            return TranslationResult(
                experiment_id=experiment_id,
                story_id=story_id,
                passage_id=passage_id,
                engine_name=self.engine_name,
                engine_version=self.engine_version,
                model_identifier=self._model_name,
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
            logger.error(
                "OPUS-MT: translation failed for passage %s: %s", passage_id, exc
            )
            return TranslationResult(
                experiment_id=experiment_id,
                story_id=story_id,
                passage_id=passage_id,
                engine_name=self.engine_name,
                engine_version=self.engine_version,
                model_identifier=self._model_name,
                context_strategy=context_strategy,
                source_text=source_text,
                supplied_context=supplied_context,
                translated_text=None,
                start_time=start_time,
                elapsed_time_ms=elapsed_ms,
                status=TranslationStatus.FAILED,
                error_message=str(exc),
                error_details={"exception_type": type(exc).__name__},
                generation_settings=gen,
            )


# ---------------------------------------------------------------------------
# Model download utility
# ---------------------------------------------------------------------------


def download_model(
    model_name: Optional[str] = None,
    model_dir: Optional[Path] = None,
) -> None:
    """
    Download the OPUS-MT model weights to the local model directory.

    This function must be called explicitly; it is NEVER called automatically
    during import or translate(). It prints progress to stdout.

    Args:
        model_name: HuggingFace model identifier. Defaults to config value.
        model_dir:  Target directory for cached weights. Defaults to config value.

    Raises:
        RuntimeError: If transformers / sentencepiece are not installed.
    """
    settings = get_settings()
    model_name = model_name or settings.opus_mt_model_name
    model_dir = Path(model_dir or settings.resolve_path(settings.opus_mt_model_dir))

    try:
        from transformers import MarianMTModel, MarianTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "Install transformers and sentencepiece before downloading:\n"
            "  pip install transformers sentencepiece"
        ) from exc

    print(f"Downloading OPUS-MT model: {model_name}")
    print(f"Destination: {model_dir}")
    model_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Downloading tokenizer for %s …", model_name)
    tokenizer = MarianTokenizer.from_pretrained(model_name)
    tokenizer.save_pretrained(str(model_dir))

    logger.info("Downloading model weights for %s …", model_name)
    model = MarianMTModel.from_pretrained(model_name)
    model.save_pretrained(str(model_dir))

    print(f"Model saved to: {model_dir}")
    logger.info("OPUS-MT model download complete → %s", model_dir)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m twi_lab.engines.opus_mt",
        description="OPUS-MT model management utility.",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download model weights to the configured local model directory.",
    )
    parser.add_argument(
        "--model-name",
        default=None,
        help="HuggingFace model ID (default: from config).",
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=None,
        help="Local directory for model weights (default: from config).",
    )
    args = parser.parse_args()
    if args.download:
        download_model(model_name=args.model_name, model_dir=args.model_dir)
    else:
        parser.print_help()
