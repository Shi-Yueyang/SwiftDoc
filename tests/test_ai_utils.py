import importlib
import json
import pytest
from unittest.mock import patch, MagicMock

from core.ai import (
    ai_prompt_for_type,
    ai_prompt_for_function,
    call_ai,
    get_ai_call_params,
    AI_FAILED,
)


class TestAiPromptForType:
    def test_struct_prompt(self):
        definition = {"kind": "struct", "members": ["int x", "int y"]}
        prompt = ai_prompt_for_type("Point", definition)
        assert "Point" in prompt
        assert "int x" in prompt
        assert "int y" in prompt
        assert "结构体" in prompt

    def test_struct_without_members(self):
        definition = {"kind": "struct", "members": []}
        prompt = ai_prompt_for_type("Empty", definition)
        assert "Empty" in prompt
        assert "无成员" in prompt

    def test_union_prompt(self):
        definition = {"kind": "union", "members": ["int x", "float y"]}
        prompt = ai_prompt_for_type("Data", definition)
        assert "Data" in prompt
        assert "联合体" in prompt

    def test_enum_prompt(self):
        definition = {"kind": "enum", "values": ["A", "B", "C"]}
        prompt = ai_prompt_for_type("Color", definition)
        assert "Color" in prompt
        assert "枚举" in prompt
        assert "A" in prompt
        assert "B" in prompt

    def test_typedef_prompt(self):
        definition = {"kind": "typedef", "original_type": "unsigned char"}
        prompt = ai_prompt_for_type("BYTE", definition)
        assert "BYTE" in prompt
        assert "unsigned char" in prompt
        assert "别名" in prompt

    def test_unknown_kind_falls_back_to_typedef(self):
        definition = {"kind": "unknown", "original_type": "int"}
        prompt = ai_prompt_for_type("MyType", definition)
        assert "MyType" in prompt
        assert "别名" in prompt


class TestAiPromptForFunction:
    def test_generates_prompt_with_params(self):
        func = {
            "name": "add",
            "inputs": [
                {"name": "a", "type": "int", "kind": "parameter"},
                {"name": "b", "type": "int", "kind": "parameter"},
            ],
            "returns": ["a + b"],
            "body_code": "return a + b;",
        }
        prompt = ai_prompt_for_function(func)
        assert "add" in prompt
        assert "a" in prompt
        assert "b" in prompt
        assert "a + b" in prompt
        assert "JSON" in prompt

    def test_generates_prompt_with_no_returns(self):
        func = {
            "name": "do_nothing",
            "inputs": [],
            "returns": [],
            "body_code": "",
        }
        prompt = ai_prompt_for_function(func)
        assert "do_nothing" in prompt
        assert "无返回值" in prompt

    def test_generates_prompt_with_global_vars(self):
        func = {
            "name": "set_mode",
            "inputs": [
                {"name": "global_mode", "type": "int", "kind": "Global variable"},
            ],
            "returns": [],
            "body_code": "global_mode = 1;",
        }
        prompt = ai_prompt_for_function(func)
        assert "set_mode" in prompt
        assert "global_mode" in prompt
        assert "Global variable" in prompt

    def test_body_code_truncated(self):
        func = {
            "name": "long_func",
            "inputs": [],
            "returns": [],
            "body_code": "x" * 2000,
        }
        prompt = ai_prompt_for_function(func)
        assert len(prompt) < 2500  # prompt shouldn't be massive


class TestGetAiCallParams:
    def test_returns_dict_with_expected_keys(self):
        params = get_ai_call_params()
        assert "temperature" in params
        assert "max_tokens" in params
        assert "retry_count" in params

    def test_params_are_numeric(self):
        params = get_ai_call_params()
        assert isinstance(params["temperature"], (int, float))
        assert isinstance(params["max_tokens"], int)
        assert isinstance(params["retry_count"], int)

    def test_cached_on_second_call(self, monkeypatch):
        call_count = [0]

        def mock_load():
            call_count[0] += 1
            return {"temperature": 1.0, "max_tokens": 800, "retry_count": 1}

        monkeypatch.setattr("core.ai.load_ai_call_params", mock_load)
        import core.ai as ai_utils

        ai_utils._cached_call_params = None
        get_ai_call_params()
        get_ai_call_params()
        assert call_count[0] == 1


class TestCallAi:
    def test_ai_failed_constant(self):
        assert AI_FAILED == "ai failed"

    def test_returns_ai_failed_when_get_client_raises(self, monkeypatch):
        monkeypatch.setattr("core.ai._get_client", MagicMock(side_effect=RuntimeError("config incomplete")))
        result = call_ai("prompt", temperature=1.0, max_tokens=100, retry_count=0)
        assert result == AI_FAILED

    def test_returns_content_on_valid_response(self, monkeypatch):
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "This is the AI response"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        monkeypatch.setattr("core.ai._get_client", lambda: (mock_client, "test-model"))
        result = call_ai("prompt", temperature=1.0, max_tokens=100, retry_count=0)
        assert result == "This is the AI response"

    def test_retries_on_empty_response(self, monkeypatch):
        mock_client = MagicMock()
        mock_choice_empty = MagicMock()
        mock_choice_empty.message.content = ""
        mock_response_empty = MagicMock()
        mock_response_empty.choices = [mock_choice_empty]

        mock_choice_valid = MagicMock()
        mock_choice_valid.message.content = "valid response"
        mock_response_valid = MagicMock()
        mock_response_valid.choices = [mock_choice_valid]

        mock_client.chat.completions.create.side_effect = [mock_response_empty, mock_response_valid]
        monkeypatch.setattr("core.ai._get_client", lambda: (mock_client, "test-model"))
        monkeypatch.setattr("core.ai.time.sleep", lambda s: None)
        result = call_ai("prompt", temperature=1.0, max_tokens=100, retry_count=1)
        assert result == "valid response"

    def test_retries_on_exception(self, monkeypatch):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [Exception("API error"), MagicMock()]
        mock_client.chat.completions.create.side_effect = Exception("API error")
        monkeypatch.setattr("core.ai._get_client", lambda: (mock_client, "test-model"))
        monkeypatch.setattr("core.ai.time.sleep", lambda s: None)
        result = call_ai("prompt", temperature=1.0, max_tokens=100, retry_count=0)
        assert result == AI_FAILED

    def test_returns_ai_failed_after_all_retries_exhausted(self, monkeypatch):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("persistent error")
        monkeypatch.setattr("core.ai._get_client", lambda: (mock_client, "test-model"))
        monkeypatch.setattr("core.ai.time.sleep", lambda s: None)
        result = call_ai("prompt", temperature=1.0, max_tokens=100, retry_count=0)
        assert result == AI_FAILED

    def test_doubles_tokens_on_retry(self, monkeypatch):
        """Verify max_tokens is doubled on retry via call_ai"""
        ai_mod = importlib.import_module("core.ai")

        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = ""
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        monkeypatch.setattr("core.ai._get_client", lambda: (mock_client, "test-model"))
        monkeypatch.setattr("core.ai.time.sleep", lambda s: None)

        # Patch call_ai itself to track token doubling
        calls = []
        original = ai_mod.call_ai

        def tracking_call(prompt, temperature, max_tokens, retry_count):
            calls.append((max_tokens, retry_count))
            return original(prompt, temperature, max_tokens, retry_count)

        monkeypatch.setattr("core.ai.call_ai", tracking_call)

        # Force AI_FAILED by making the retry also fail
        monkeypatch.setattr("core.ai._get_client", lambda: MagicMock(side_effect=RuntimeError("no config")))

        ai_mod.call_ai("prompt", temperature=1.0, max_tokens=100, retry_count=2)
        assert calls[0] == (100, 2)
        assert calls[1][0] == 200  # doubled
        assert calls[1][1] == 1
        assert calls[2][0] == 400  # doubled again
        assert calls[2][1] == 0
