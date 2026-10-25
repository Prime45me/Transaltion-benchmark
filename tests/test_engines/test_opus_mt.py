"""
Tests for the OPUS-MT engine adapter.

All transformers / torch calls are mocked using unittest.mock — no model
weights are downloaded and no GPU is required.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from twi_lab.schemas import TranslationStatus


# ---------------------------------------------------------------------------
# Helpers — build fake transformers module in sys.modules
# ---------------------------------------------------------------------------

def _make_mock_transformers(decoded_output: str = "Ɔkɔkɔ no anka dua no mu.") -> MagicMock:
    """Return a MagicMock that looks like the transformers package."""
    mock_transformers = MagicMock()

    mock_tokenizer = MagicMock()
    mock_tokenizer.return_value = {"input_ids": MagicMock(), "attention_mask": MagicMock()}
    mock_tokenizer.decode.return_value = decoded_output

    # __call__ returns dict-like inputs accepted by model.generate
    mock_tokenizer_instance = MagicMock()
    mock_tokenizer_instance.decode.return_value = decoded_output
    mock_tokenizer_instance.return_value = {"input_ids": MagicMock()}

    mock_model_instance = MagicMock()
    mock_model_instance.generate.return_value = [MagicMock()]
    mock_model_instance.eval.return_value = None

    mock_transformers.MarianTokenizer.from_pretrained.return_value = mock_tokenizer_instance
    mock_transformers.MarianMTModel.from_pretrained.return_value = mock_model_instance

    return mock_transformers, mock_tokenizer_instance, mock_model_instance


def _make_mock_torch() -> MagicMock:
    """Return a MagicMock that stubs torch.no_grad()."""
    mock_torch = MagicMock()
    mock_torch.no_grad.return_value.__enter__ = MagicMock(return_value=None)
    mock_torch.no_grad.return_value.__exit__ = MagicMock(return_value=False)
    return mock_torch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def model_dir(tmp_path: Path) -> Path:
    """Create a temporary directory that pretends to hold model weights."""
    d = tmp_path / "opus-mt-en-tw"
    d.mkdir()
    return d


@pytest.fixture()
def adapter(model_dir: Path):
    """Return an OPUSMTAdapter pointing at the fake model directory."""
    from twi_lab.engines.opus_mt import OPUSMTAdapter
    return OPUSMTAdapter(
        model_name="Helsinki-NLP/opus-mt-en-tw",
        model_dir=model_dir,
        device="cpu",
    )


TRANSLATE_KWARGS = dict(
    experiment_id="exp-001",
    story_id="STORY-T01",
    passage_id="STORY-T01-P01",
)


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------

class TestOPUSMTAvailability:

    def test_available_when_transformers_installed_and_model_dir_exists(
        self, adapter, model_dir
    ):
        with patch.dict(sys.modules, {"transformers": MagicMock()}):
            assert adapter.is_available is True

    def test_not_available_when_transformers_missing(self, adapter):
        # Set transformers to None in sys.modules — Python treats this as
        # 'module exists but is blocked', causing ImportError on import.
        with patch.dict(sys.modules, {"transformers": None}):
            from twi_lab.engines.opus_mt import OPUSMTAdapter as _A
            fresh = _A(model_dir=adapter._model_dir)
            assert fresh.is_available is False

    def test_not_available_when_model_dir_missing(self, tmp_path):
        from twi_lab.engines.opus_mt import OPUSMTAdapter
        with patch.dict(sys.modules, {"transformers": MagicMock()}):
            adapter = OPUSMTAdapter(model_dir=tmp_path / "nonexistent")
            assert adapter.is_available is False


# ---------------------------------------------------------------------------
# engine identity
# ---------------------------------------------------------------------------

class TestOPUSMTIdentity:

    def test_engine_name(self, adapter):
        assert adapter.engine_name == "opus-mt"

    def test_engine_version_is_string(self, adapter):
        assert isinstance(adapter.engine_version, str)

    def test_repr_contains_engine_name(self, adapter):
        assert "opus-mt" in repr(adapter)


# ---------------------------------------------------------------------------
# translate() — success path (model fully mocked)
# ---------------------------------------------------------------------------

class TestOPUSMTTranslateSuccess:

    def test_translate_returns_success_status(self, adapter, model_dir):
        mock_tf, mock_tok, mock_model = _make_mock_transformers("Ɔkɔ no anka.")
        mock_torch = _make_mock_torch()

        with patch.dict(sys.modules, {"transformers": mock_tf, "torch": mock_torch}):
            adapter._model = mock_model
            adapter._tokenizer = mock_tok

            result = adapter.translate(
                "The bird sang in the tree.",
                **TRANSLATE_KWARGS,
            )

        assert result.status == TranslationStatus.SUCCESS

    def test_translate_populates_engine_metadata(self, adapter):
        mock_tf, mock_tok, mock_model = _make_mock_transformers()
        mock_torch = _make_mock_torch()

        with patch.dict(sys.modules, {"transformers": mock_tf, "torch": mock_torch}):
            adapter._model = mock_model
            adapter._tokenizer = mock_tok
            result = adapter.translate("Hello.", **TRANSLATE_KWARGS)

        assert result.engine_name == "opus-mt"
        assert result.engine_version is not None
        assert result.model_identifier == "Helsinki-NLP/opus-mt-en-tw"

    def test_translate_source_text_unchanged(self, adapter):
        mock_tf, mock_tok, mock_model = _make_mock_transformers()
        mock_torch = _make_mock_torch()
        source = "Ama walked to the market."

        with patch.dict(sys.modules, {"transformers": mock_tf, "torch": mock_torch}):
            adapter._model = mock_model
            adapter._tokenizer = mock_tok
            result = adapter.translate(source, **TRANSLATE_KWARGS)

        assert result.source_text == source

    def test_translate_records_elapsed_time(self, adapter):
        mock_tf, mock_tok, mock_model = _make_mock_transformers()
        mock_torch = _make_mock_torch()

        with patch.dict(sys.modules, {"transformers": mock_tf, "torch": mock_torch}):
            adapter._model = mock_model
            adapter._tokenizer = mock_tok
            result = adapter.translate("A sentence.", **TRANSLATE_KWARGS)

        assert result.elapsed_time_ms is not None
        assert result.elapsed_time_ms >= 0

    def test_translate_populates_passage_ids(self, adapter):
        mock_tf, mock_tok, mock_model = _make_mock_transformers()
        mock_torch = _make_mock_torch()

        with patch.dict(sys.modules, {"transformers": mock_tf, "torch": mock_torch}):
            adapter._model = mock_model
            adapter._tokenizer = mock_tok
            result = adapter.translate("Test.", **TRANSLATE_KWARGS)

        assert result.experiment_id == "exp-001"
        assert result.story_id == "STORY-T01"
        assert result.passage_id == "STORY-T01-P01"

    def test_translate_source_char_count_auto_filled(self, adapter):
        mock_tf, mock_tok, mock_model = _make_mock_transformers()
        mock_torch = _make_mock_torch()
        source = "The child laughed."

        with patch.dict(sys.modules, {"transformers": mock_tf, "torch": mock_torch}):
            adapter._model = mock_model
            adapter._tokenizer = mock_tok
            result = adapter.translate(source, **TRANSLATE_KWARGS)

        assert result.source_character_count == len(source)


# ---------------------------------------------------------------------------
# translate() — failure paths (never raise; always return FAILED)
# ---------------------------------------------------------------------------

class TestOPUSMTTranslateFailure:

    def test_model_dir_missing_returns_failed(self, tmp_path):
        from twi_lab.engines.opus_mt import OPUSMTAdapter
        adapter = OPUSMTAdapter(model_dir=tmp_path / "missing_weights")
        mock_tf = MagicMock()

        with patch.dict(sys.modules, {"transformers": mock_tf}):
            result = adapter.translate("Hello.", **TRANSLATE_KWARGS)

        assert result.status == TranslationStatus.FAILED
        assert result.error_message is not None
        assert result.translated_text is None

    def test_model_load_error_returns_failed(self, adapter, model_dir):
        mock_tf = MagicMock()
        mock_tf.MarianMTModel.from_pretrained.side_effect = OSError("Corrupt model file.")

        with patch.dict(sys.modules, {"transformers": mock_tf}):
            result = adapter.translate("Hello.", **TRANSLATE_KWARGS)

        assert result.status == TranslationStatus.FAILED
        assert "Corrupt model file" in result.error_message

    def test_runtime_error_during_generate_returns_failed(self, adapter, model_dir):
        mock_tf, mock_tok, mock_model = _make_mock_transformers()
        mock_torch = _make_mock_torch()
        mock_model.generate.side_effect = RuntimeError("CUDA out of memory.")

        with patch.dict(sys.modules, {"transformers": mock_tf, "torch": mock_torch}):
            adapter._model = mock_model
            adapter._tokenizer = mock_tok
            result = adapter.translate("A long story.", **TRANSLATE_KWARGS)

        assert result.status == TranslationStatus.FAILED
        assert "CUDA out of memory" in result.error_message
        assert result.error_details["exception_type"] == "RuntimeError"

    def test_translate_never_raises(self, adapter, model_dir):
        """translate() must not propagate exceptions — always returns a result."""
        mock_tf = MagicMock()
        mock_tf.MarianTokenizer.from_pretrained.side_effect = Exception("Unexpected!")

        with patch.dict(sys.modules, {"transformers": mock_tf}):
            # Should not raise — must return a FAILED result
            result = adapter.translate("Test.", **TRANSLATE_KWARGS)

        assert result is not None
        assert result.status == TranslationStatus.FAILED


# ---------------------------------------------------------------------------
# download_model — does NOT actually download anything in tests
# ---------------------------------------------------------------------------

class TestOPUSMTDownload:

    def test_download_raises_when_transformers_missing(self, tmp_path):
        from twi_lab.engines.opus_mt import download_model
        with patch.dict(sys.modules, {"transformers": None}):
            with patch("builtins.__import__", side_effect=ImportError("no transformers")):
                with pytest.raises(RuntimeError, match="transformers"):
                    download_model(model_dir=tmp_path / "model")

    def test_download_saves_model_to_directory(self, tmp_path):
        from twi_lab.engines.opus_mt import download_model
        mock_tf = MagicMock()
        mock_tok_inst = MagicMock()
        mock_model_inst = MagicMock()
        mock_tf.MarianTokenizer.from_pretrained.return_value = mock_tok_inst
        mock_tf.MarianMTModel.from_pretrained.return_value = mock_model_inst

        target = tmp_path / "opus-model"
        with patch.dict(sys.modules, {"transformers": mock_tf}):
            download_model(
                model_name="Helsinki-NLP/opus-mt-en-tw",
                model_dir=target,
            )

        mock_tok_inst.save_pretrained.assert_called_once_with(str(target))
        mock_model_inst.save_pretrained.assert_called_once_with(str(target))
