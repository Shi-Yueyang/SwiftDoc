import os
import json
import sys
import tempfile
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock, mock_open

from config.manager import (
    get_config_path,
    load_user_config,
    load_ai_call_params,
    merge_config_sources,
    is_ai_config_complete,
    get_missing_ai_keys,
    resolve_ai_config,
    save_user_config,
    set_config_value,
    _normalize_config,
    _normalize_optional_config,
    _read_json_file,
    _ensure_optional_config_defaults,
    OPTIONAL_CONFIG_DEFAULTS,
    OPTIONAL_CONFIG_TYPES,
)


class TestGetConfigPath:
    def test_returns_path_object(self):
        path = get_config_path()
        assert path is not None

    def test_path_contains_aoto_md(self):
        path = get_config_path()
        assert "aoto-md" in str(path) or "aoto-md" == path.parent.name

    def test_path_ends_with_config_json(self):
        path = get_config_path()
        assert path.name == "config.json"

    @patch("platform.system", return_value="Windows")
    def test_windows_base_dir(self, mock_system):
        path = get_config_path()
        assert "Roaming" in str(path) or "APPDATA" in os.environ

    @patch("platform.system", return_value="Darwin")
    def test_macos_base_dir(self, mock_system):
        path = get_config_path()
        assert "Application Support" in str(path)

    @patch("platform.system", return_value="Linux")
    def test_linux_base_dir(self, mock_system):
        path = get_config_path()
        assert ".config" in str(path)


class TestNormalizeConfig:
    def test_extracts_expected_keys(self):
        raw = {"api_key": "sk-key", "base_url": "https://api.openai.com/v1", "model_name": "gpt-4"}
        mapping = {"api_key": "api_key", "base_url": "base_url", "model_name": "model_name"}
        result = _normalize_config(raw, mapping)
        assert result == raw

    def test_skips_none_values(self):
        raw = {"api_key": None, "base_url": "https://api.openai.com/v1", "model_name": "gpt-4"}
        mapping = {"api_key": "api_key", "base_url": "base_url", "model_name": "model_name"}
        result = _normalize_config(raw, mapping)
        assert "api_key" not in result
        assert result["base_url"] == "https://api.openai.com/v1"

    def test_strips_values(self):
        raw = {"api_key": "  key-with-spaces  ", "base_url": "url", "model_name": ""}
        mapping = {"api_key": "api_key", "base_url": "base_url", "model_name": "model_name"}
        result = _normalize_config(raw, mapping)
        assert result.get("api_key") == "key-with-spaces"
        assert "model_name" not in result  # empty after strip

    def test_skips_unknown_keys(self):
        raw = {"api_key": "key", "extra_field": "value"}
        mapping = {"api_key": "api_key"}
        result = _normalize_config(raw, mapping)
        assert "extra_field" not in result


class TestNormalizeOptionalConfig:
    def test_returns_defaults_for_empty_config(self):
        result = _normalize_optional_config({})
        assert result["temperature"] == OPTIONAL_CONFIG_DEFAULTS["temperature"]
        assert result["max_tokens"] == OPTIONAL_CONFIG_DEFAULTS["max_tokens"]
        assert result["retry_count"] == OPTIONAL_CONFIG_DEFAULTS["retry_count"]

    def test_returns_defaults_for_none_values(self):
        result = _normalize_optional_config({"temperature": None, "max_tokens": None, "retry_count": None})
        assert result["temperature"] == OPTIONAL_CONFIG_DEFAULTS["temperature"]

    def test_converts_types(self):
        result = _normalize_optional_config({"temperature": "0.7", "max_tokens": "1024", "retry_count": "3"})
        assert result["temperature"] == 0.7
        assert isinstance(result["temperature"], float)
        assert result["max_tokens"] == 1024
        assert isinstance(result["max_tokens"], int)
        assert result["retry_count"] == 3
        assert isinstance(result["retry_count"], int)

    def test_fallback_on_invalid_value(self):
        result = _normalize_optional_config({"temperature": "not_a_number", "max_tokens": "also_bad"})
        assert result["temperature"] == OPTIONAL_CONFIG_DEFAULTS["temperature"]
        assert result["max_tokens"] == OPTIONAL_CONFIG_DEFAULTS["max_tokens"]


class TestReadJsonFile:
    def test_reads_valid_json(self, tmp_path):
        path = tmp_path / "test.json"
        path.write_text('{"key": "value"}')
        result = _read_json_file(path)
        assert result == {"key": "value"}

    def test_returns_empty_dict_for_missing_file(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        result = _read_json_file(path)
        assert result == {}

    def test_raises_on_invalid_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json")
        with pytest.raises(RuntimeError, match="not valid JSON"):
            _read_json_file(path)


class TestLoadUserConfig:
    def test_loads_complete_config(self, mock_config_json):
        config, path = load_user_config(Path(mock_config_json))
        assert config["api_key"] == "sk-test-key"
        assert config["base_url"] == "https://api.example.com/v1"
        assert config["model_name"] == "test-model"
        assert config["temperature"] == 0.7
        assert config["max_tokens"] == 1024
        assert config["retry_count"] == 2

    def test_returns_empty_dict_for_empty_config(self, empty_config_json):
        config, path = load_user_config(Path(empty_config_json))
        assert config == {}
        assert path == Path(empty_config_json)

    def test_returns_empty_dict_for_missing_file(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        config, cfg_path = load_user_config(path)
        assert config == {}


class TestLoadAiCallParams:
    def test_loads_params(self, mock_config_json):
        params = load_ai_call_params(Path(mock_config_json))
        assert params["temperature"] == 0.7
        assert params["max_tokens"] == 1024
        assert params["retry_count"] == 2

    def test_uses_defaults_for_empty_config(self, empty_config_json):
        params = load_ai_call_params(Path(empty_config_json))
        assert params["temperature"] == OPTIONAL_CONFIG_DEFAULTS["temperature"]
        assert params["max_tokens"] == OPTIONAL_CONFIG_DEFAULTS["max_tokens"]
        assert params["retry_count"] == OPTIONAL_CONFIG_DEFAULTS["retry_count"]


class TestMergeConfigSources:
    def test_first_source_wins(self):
        s1 = ("source1", {"api_key": "key1", "base_url": "url1"})
        s2 = ("source2", {"api_key": "key2", "model_name": "model2"})
        merged, origins = merge_config_sources(s1, s2)
        assert merged["api_key"] == "key1"
        assert merged["base_url"] == "url1"
        assert merged["model_name"] == "model2"
        assert origins["api_key"] == "source1"
        assert origins["model_name"] == "source2"

    def test_empty_value_is_skipped(self):
        s1 = ("source1", {"api_key": ""})
        s2 = ("source2", {"api_key": "key2"})
        merged, origins = merge_config_sources(s1, s2)
        assert merged["api_key"] == "key2"
        assert origins["api_key"] == "source2"


class TestIsAiConfigComplete:
    def test_complete(self):
        assert is_ai_config_complete({"api_key": "k", "base_url": "u", "model_name": "m"})

    def test_missing_key(self):
        assert not is_ai_config_complete({"api_key": "k", "base_url": "u"})

    def test_empty_key(self):
        assert not is_ai_config_complete({"api_key": "", "base_url": "u", "model_name": "m"})

    def test_all_missing(self):
        assert not is_ai_config_complete({})


class TestGetMissingAiKeys:
    def test_no_missing(self):
        assert get_missing_ai_keys({"api_key": "k", "base_url": "u", "model_name": "m"}) == []

    def test_some_missing(self):
        missing = get_missing_ai_keys({"api_key": "k"})
        assert "base_url" in missing
        assert "model_name" in missing

    def test_all_missing(self):
        missing = get_missing_ai_keys({})
        assert len(missing) == 3
        assert "api_key" in missing
        assert "base_url" in missing
        assert "model_name" in missing


class TestResolveAiConfig:
    def test_resolves_user_config(self, monkeypatch):
        mock_json = {"api_key": "test-key", "base_url": "https://test.com", "model_name": "test-model"}
        monkeypatch.setattr("config.manager.load_user_config", lambda *a, **kw: (mock_json, "/fake/path"))
        config, details = resolve_ai_config()
        assert config["api_key"] == "test-key"
        assert details["config_path"] == "/fake/path"

    def test_resolves_empty_config(self, monkeypatch):
        monkeypatch.setattr("config.manager.load_user_config", lambda *a, **kw: ({}, "/fake/path"))
        config, details = resolve_ai_config()
        assert config == {}


class TestSaveUserConfig:
    def test_saves_to_path(self, tmp_path):
        config_path = tmp_path / "aoto-md" / "config.json"
        config = {"api_key": "sk-test", "base_url": "https://api.test.com", "model_name": "test-model"}
        saved_path = save_user_config(config, config_path)
        assert saved_path == config_path
        assert config_path.exists()
        with open(config_path) as f:
            data = json.load(f)
        assert data["api_key"] == "sk-test"

    def test_preserves_existing_optional_keys(self, tmp_path):
        config_path = tmp_path / "aoto-md" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"api_key": "old", "base_url": "u", "model_name": "m", "temperature": 0.9}')
        config = {"api_key": "new", "base_url": "u", "model_name": "m"}
        save_user_config(config, config_path)
        with open(config_path) as f:
            data = json.load(f)
        assert data["api_key"] == "new"
        assert data["temperature"] == 0.9


class TestSetConfigValue:
    def test_sets_required_key(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{}")
        result = set_config_value("api_key", "my-key", config_path)
        with open(config_path) as f:
            data = json.load(f)
        assert data["api_key"] == "my-key"

    def test_sets_optional_key_with_type_conversion(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{}")
        result = set_config_value("temperature", "0.5", config_path)
        with open(config_path) as f:
            data = json.load(f)
        assert data["temperature"] == 0.5

    def test_rejects_unknown_key(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{}")
        with pytest.raises(ValueError, match="Unknown config key"):
            set_config_value("nonexistent_key", "value", config_path)

    def test_rejects_invalid_type(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{}")
        with pytest.raises(ValueError, match="Invalid value"):
            set_config_value("max_tokens", "not_an_integer", config_path)
