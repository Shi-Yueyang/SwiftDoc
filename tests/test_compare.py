import sys
import os
import json
import pytest

from core.compare import compare_functions, compare_types


class TestCompareFunctions:
    def test_empty_both(self):
        result = compare_functions([], [])
        assert result == {"added": [], "modified": [], "removed": []}

    def test_added_function(self):
        old = [{"name": "foo", "normalized_body": "abc"}]
        new = [{"name": "foo", "normalized_body": "abc"}, {"name": "bar", "normalized_body": "xyz"}]
        result = compare_functions(old, new)
        assert len(result["added"]) == 1
        assert result["added"][0]["name"] == "bar"
        assert result["modified"] == []
        assert result["removed"] == []

    def test_removed_function(self):
        old = [{"name": "foo", "normalized_body": "abc"}, {"name": "bar", "normalized_body": "xyz"}]
        new = [{"name": "foo", "normalized_body": "abc"}]
        result = compare_functions(old, new)
        assert len(result["removed"]) == 1
        assert result["removed"][0]["name"] == "bar"
        assert result["added"] == []
        assert result["modified"] == []

    def test_modified_function_body(self):
        old = [{"name": "foo", "normalized_body": "abc"}]
        new = [{"name": "foo", "normalized_body": "def"}]
        result = compare_functions(old, new)
        assert len(result["modified"]) == 1
        assert result["modified"][0]["old"]["name"] == "foo"
        assert result["modified"][0]["new"]["name"] == "foo"
        assert result["modified"][0]["old"]["normalized_body"] == "abc"
        assert result["modified"][0]["new"]["normalized_body"] == "def"
        assert result["added"] == []
        assert result["removed"] == []

    def test_unchanged_function_no_normalized_body(self):
        old = [{"name": "foo"}]
        new = [{"name": "foo"}]
        result = compare_functions(old, new)
        assert result == {"added": [], "modified": [], "removed": []}

    def test_unchanged_function_same_body(self):
        old = [{"name": "foo", "normalized_body": "same"}]
        new = [{"name": "foo", "normalized_body": "same"}]
        result = compare_functions(old, new)
        assert result["modified"] == []

    def test_mixed_changes(self):
        old = [
            {"name": "keep", "normalized_body": "k"},
            {"name": "modify", "normalized_body": "old_body"},
            {"name": "remove_me", "normalized_body": "r"},
        ]
        new = [
            {"name": "keep", "normalized_body": "k"},
            {"name": "modify", "normalized_body": "new_body"},
            {"name": "new_func", "normalized_body": "n"},
        ]
        result = compare_functions(old, new)
        assert [f["name"] for f in result["added"]] == ["new_func"]
        assert [m["old"]["name"] for m in result["modified"]] == ["modify"]
        assert [f["name"] for f in result["removed"]] == ["remove_me"]

    def test_functions_without_normalized_body_default_empty(self):
        old = [{"name": "foo"}, {"name": "bar"}]
        new = [{"name": "foo", "some_other_field": True}, {"name": "bar"}]
        result = compare_functions(old, new)
        assert result["modified"] == []


class TestCompareTypes:
    def test_empty_both(self):
        result = compare_types({}, {})
        assert result == {"added": {}, "modified": {}, "removed": {}}

    def test_added_type(self):
        old = {"A": {"kind": "struct", "members": ["int x"]}}
        new = {"A": {"kind": "struct", "members": ["int x"]}, "B": {"kind": "enum", "values": ["V1"]}}
        result = compare_types(old, new)
        assert list(result["added"].keys()) == ["B"]
        assert result["modified"] == {}
        assert result["removed"] == {}

    def test_removed_type(self):
        old = {"A": {"kind": "struct"}, "B": {"kind": "enum"}}
        new = {"A": {"kind": "struct"}}
        result = compare_types(old, new)
        assert list(result["removed"].keys()) == ["B"]
        assert result["added"] == {}
        assert result["modified"] == {}

    def test_modified_type(self):
        old = {"A": {"kind": "struct", "members": ["int x"]}}
        new = {"A": {"kind": "struct", "members": ["int x", "int y"]}}
        result = compare_types(old, new)
        assert list(result["modified"].keys()) == ["A"]

    def test_type_description_change_is_ignored(self):
        old = {"A": {"kind": "struct", "members": ["int x"], "type_description": "old desc"}}
        new = {"A": {"kind": "struct", "members": ["int x"], "type_description": "new desc"}}
        result = compare_types(old, new)
        assert result["modified"] == {}

    def test_unchanged_type(self):
        old = {"A": {"kind": "typedef", "original_type": "int"}}
        new = {"A": {"kind": "typedef", "original_type": "int"}}
        result = compare_types(old, new)
        assert result == {"added": {}, "modified": {}, "removed": {}}

    def test_source_file_change_is_ignored(self):
        old = {"A": {"kind": "struct", "members": ["int x"], "source_file": "a.h"}}
        new = {"A": {"kind": "struct", "members": ["int x"], "source_file": "b.h"}}
        result = compare_types(old, new)
        assert result["modified"] == {}

    def test_comment_change_is_ignored(self):
        old = {"A": {"kind": "struct", "members": ["int x"], "comment": "old comment"}}
        new = {"A": {"kind": "struct", "members": ["int x"], "comment": "new comment"}}
        result = compare_types(old, new)
        assert result["modified"] == {}

    def test_type_rename_correlation_transfers_description(self):
        old = {"OldName": {"kind": "struct", "members": ["int x"], "type_description": "desc"}}
        new = {"NewName": {"kind": "struct", "members": ["int x"]}}
        result = compare_types(old, new)
        assert "OldName" not in result["removed"]
        assert result["added"]["NewName"]["type_description"] == "desc"

    def test_function_with_same_name_different_file_treated_separately(self):
        old = [{"name": "helper", "file": "a.c", "normalized_body": "bodyA"}]
        new = [{"name": "helper", "file": "b.c", "normalized_body": "bodyA"}]
        result = compare_functions(old, new)
        assert len(result["added"]) == 1
        assert len(result["removed"]) == 1
        assert result["added"][0]["file"] == "b.c"

    def test_function_rename_correlation_transfers_descriptions(self):
        old = [{"name": "old_func", "file": "a.c", "normalized_body": "bodyX", "algorithm_logic": "logic"}]
        new_list = [{"name": "new_func", "file": "a.c", "normalized_body": "bodyX"}]
        result = compare_functions(old, new_list)
        assert len(result["added"]) == 1
        assert len(result["removed"]) == 1
        assert new_list[0]["algorithm_logic"] == "logic"
        assert new_list[0].get("_renamed_from") == "old_func"

    def test_param_type_change_triggers_modification(self):
        old = [{"name": "foo", "normalized_body": "body", "inputs": [
            {"name": "x", "kind": "parameter", "type": "int", "direction": "in"},
        ]}]
        new = [{"name": "foo", "normalized_body": "body", "inputs": [
            {"name": "x", "kind": "parameter", "type": "float", "direction": "in"},
        ]}]
        result = compare_functions(old, new)
        assert len(result["modified"]) == 1

    def test_param_name_change_triggers_modification(self):
        old = [{"name": "foo", "normalized_body": "body", "inputs": [
            {"name": "x", "kind": "parameter", "type": "int", "direction": "in"},
        ]}]
        new = [{"name": "foo", "normalized_body": "body", "inputs": [
            {"name": "y", "kind": "parameter", "type": "int", "direction": "in"},
        ]}]
        result = compare_functions(old, new)
        assert len(result["modified"]) == 1

    def test_param_direction_change_triggers_modification(self):
        old = [{"name": "foo", "normalized_body": "body", "inputs": [
            {"name": "p", "kind": "parameter", "type": "int*", "direction": "in"},
        ]}]
        new = [{"name": "foo", "normalized_body": "body", "inputs": [
            {"name": "p", "kind": "parameter", "type": "int*", "direction": "out"},
        ]}]
        result = compare_functions(old, new)
        assert len(result["modified"]) == 1

    def test_return_type_change_triggers_modification(self):
        old = [{"name": "foo", "return_type": "int", "normalized_body": "body"}]
        new = [{"name": "foo", "return_type": "void", "normalized_body": "body"}]
        result = compare_functions(old, new)
        assert len(result["modified"]) == 1

    def test_param_added_triggers_modification(self):
        old = [{"name": "foo", "normalized_body": "body", "inputs": [
            {"name": "x", "kind": "parameter", "type": "int", "direction": "in"},
        ]}]
        new = [{"name": "foo", "normalized_body": "body", "inputs": [
            {"name": "x", "kind": "parameter", "type": "int", "direction": "in"},
            {"name": "y", "kind": "parameter", "type": "int", "direction": "in"},
        ]}]
        result = compare_functions(old, new)
        assert len(result["modified"]) == 1

    def test_signature_unchanged_body_same_not_modified(self):
        old = [{"name": "foo", "return_type": "int", "normalized_body": "body", "inputs": [
            {"name": "x", "kind": "parameter", "type": "int", "direction": "in"},
        ]}]
        new = [{"name": "foo", "return_type": "int", "normalized_body": "body", "inputs": [
            {"name": "x", "kind": "parameter", "type": "int", "direction": "in"},
        ]}]
        result = compare_functions(old, new)
        assert result["modified"] == []

    def test_global_var_input_change_ignored_in_signature(self):
        old = [{"name": "foo", "normalized_body": "body", "inputs": [
            {"name": "g_flag", "kind": "Global variable", "type": "int", "direction": "in"},
        ]}]
        new = [{"name": "foo", "normalized_body": "body", "inputs": [
            {"name": "g_flag", "kind": "Global variable", "type": "int", "direction": "in out"},
        ]}]
        result = compare_functions(old, new)
        assert result["modified"] == []

    def test_body_and_signature_both_change(self):
        old = [{"name": "foo", "return_type": "int", "normalized_body": "old", "inputs": [
            {"name": "x", "kind": "parameter", "type": "int", "direction": "in"},
        ]}]
        new = [{"name": "foo", "return_type": "void", "normalized_body": "new", "inputs": [
            {"name": "x", "kind": "parameter", "type": "float", "direction": "out"},
        ]}]
        result = compare_functions(old, new)
        assert len(result["modified"]) == 1

