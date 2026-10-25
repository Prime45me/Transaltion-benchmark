"""
Tests for config.py — Settings loading, defaults, validation, path resolution,
and environment variable overrides.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from twi_lab.config import Settings, get_settings


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


class TestSettingsDefaults:

    def test_default_project_env(self):
        s = Settings()
        assert s.project_env == "development"

    def test_default_log_level(self):
        s = Settings()
        assert s.log_level == "INFO"

    def test_default_dataset_path(self):
        s = Settings()
        assert s.dataset_path == Path("data/samples/passages.jsonl")

    def test_default_manifest_path(self):
        s = Settings()
        assert s.manifest_path == Path("data/samples/manifest.json")

    def test_default_results_dir(self):
        s = Settings()
        assert str(s.results_dir) == "results"

    def test_khaya_api_key_defaults_to_none(self):
        s = Settings(_env_file=None)
        assert s.khaya_api_key is None

    def test_khaya_api_secondary_key_defaults_to_none(self):
        s = Settings(_env_file=None)
        assert s.khaya_api_secondary_key is None

    def test_opus_mt_model_name_default(self):
        s = Settings()
        assert s.opus_mt_model_name == "Helsinki-NLP/opus-mt-en-tw"

    def test_local_device_defaults_to_cpu(self):
        s = Settings()
        assert s.local_device == "cpu"


# ---------------------------------------------------------------------------
# Log level validation
# ---------------------------------------------------------------------------


class TestLogLevelValidation:

    @pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    def test_valid_log_levels_accepted(self, level):
        s = Settings(log_level=level)
        assert s.log_level == level

    @pytest.mark.parametrize("level", ["debug", "info", "warning"])
    def test_lowercase_log_levels_normalised(self, level):
        s = Settings(log_level=level)
        assert s.log_level == level.upper()

    def test_invalid_log_level_raises(self):
        with pytest.raises((ValidationError, ValueError)):
            Settings(log_level="VERBOSE")


# ---------------------------------------------------------------------------
# Environment variable overrides
# ---------------------------------------------------------------------------


class TestEnvironmentVariableOverrides:

    def test_log_level_overridden_by_env(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}, clear=False):
            s = Settings()
            assert s.log_level == "DEBUG"

    def test_project_env_overridden_by_env(self):
        with patch.dict(os.environ, {"PROJECT_ENV": "testing"}, clear=False):
            s = Settings()
            assert s.project_env == "testing"

    def test_dataset_path_overridden_by_env(self):
        with patch.dict(os.environ, {"DATASET_PATH": "custom/data.jsonl"}, clear=False):
            s = Settings()
            assert s.dataset_path == Path("custom/data.jsonl")

    def test_khaya_api_key_from_env(self):
        with patch.dict(os.environ, {"KHAYA_API_KEY": "sk-testkey123"}, clear=False):
            s = Settings()
            assert s.khaya_api_key == "sk-testkey123"

    def test_invalid_project_env_raises(self):
        with patch.dict(os.environ, {"PROJECT_ENV": "staging"}, clear=False):
            with pytest.raises((ValidationError, ValueError)):
                Settings()


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


class TestPathResolution:

    def test_resolved_dataset_path_is_absolute(self):
        s = Settings()
        assert s.resolved_dataset_path.is_absolute()

    def test_resolved_manifest_path_is_absolute(self):
        s = Settings()
        assert s.resolved_manifest_path.is_absolute()

    def test_resolved_results_dir_is_absolute(self):
        s = Settings()
        assert s.resolved_results_dir.is_absolute()

    def test_resolved_logs_dir_is_absolute(self):
        s = Settings()
        assert s.resolved_logs_dir.is_absolute()

    def test_resolve_path_with_absolute_path(self, tmp_path):
        s = Settings()
        result = s.resolve_path(tmp_path)
        assert result == tmp_path

    def test_resolve_path_relative_anchors_to_base_dir(self):
        s = Settings()
        result = s.resolve_path(Path("data/samples/passages.jsonl"))
        assert result.is_absolute()
        assert result == s.base_dir / "data" / "samples" / "passages.jsonl"

    def test_base_dir_is_absolute(self):
        s = Settings()
        assert s.base_dir.is_absolute()


# ---------------------------------------------------------------------------
# Singleton / cache
# ---------------------------------------------------------------------------


class TestGetSettingsSingleton:

    def test_get_settings_returns_settings_instance(self):
        s = get_settings()
        assert isinstance(s, Settings)

    def test_get_settings_returns_same_object(self):
        """lru_cache should return the same singleton instance."""
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
