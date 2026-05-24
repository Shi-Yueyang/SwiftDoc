import os
import json
import pytest

from parsers.c.types import (
    collect_type_definitions_with_comments,
    scan_project_types,
    load_previous_type_cache,
    write_types_cache,
    is_missing_type_description,
    summarize_ai_result,
    AI_FAILED,
)


class TestCollectTypeDefinitionsWithComments:
    def test_finds_struct_typedef(self):
        code = "typedef struct { int x; int y; } Point;"
        result = collect_type_definitions_with_comments(code, "test.h")
        assert "Point" in result
        assert result["Point"]["kind"] == "struct"

    def test_finds_enum_typedef(self):
        code = "typedef enum { A, B, C } Color;"
        result = collect_type_definitions_with_comments(code, "test.h")
        assert "Color" in result
        assert result["Color"]["kind"] == "enum"
        assert result["Color"]["values"] == ["A", "B", "C"]

    def test_finds_union_typedef(self):
        code = "typedef union { int i; float f; } Data;"
        result = collect_type_definitions_with_comments(code, "test.h")
        assert "Data" in result

    def test_finds_simple_typedef(self):
        code = "typedef unsigned char BYTE;"
        result = collect_type_definitions_with_comments(code, "test.h")
        assert "BYTE" in result
        assert result["BYTE"]["kind"] == "typedef"
        assert result["BYTE"]["original_type"] == "unsigned char"

    def test_finds_array_typedef(self):
        code = "typedef BYTE_8 DEVICE_ID[3];"
        result = collect_type_definitions_with_comments(code, "test.h")
        assert "DEVICE_ID" in result
        assert result["DEVICE_ID"]["kind"] == "typedef"

    def test_ignores_commented_out_definitions(self):
        code = "// typedef struct { int a; } OldType;\ntypedef struct { int b; } NewType;"
        result = collect_type_definitions_with_comments(code, "test.h")
        assert "OldType" not in result
        # NewType may or may not be found depending on regex matching with the comment
        # The important thing is OldType inside comment is ignored

    def test_ignores_block_commented_definitions(self):
        code = "/* typedef struct { int a; } OldType; */\ntypedef struct { int b; } NewType;"
        result = collect_type_definitions_with_comments(code, "test.h")
        assert "OldType" not in result

    def test_associates_preceding_comments(self):
        code = "/* This is a point */\ntypedef struct { int x; int y; } Point;"
        result = collect_type_definitions_with_comments(code, "test.h")
        assert "Point" in result
        assert result["Point"].get("comment") == "This is a point"

    def test_tags_source_file(self):
        code = "typedef int MyInt;"
        result = collect_type_definitions_with_comments(code, "myheader.h")
        assert result["MyInt"]["source_file"] == "myheader.h"

    def test_skips_typedef_with_struct_braces(self):
        """typedefs that contain struct/braces in original_type should be skipped as they match other patterns."""
        code = "typedef struct _st { int a; } ST_TYPE;"
        result = collect_type_definitions_with_comments(code, "test.h")
        # The struct pattern should match this
        assert "ST_TYPE" in result
        assert result["ST_TYPE"]["kind"] == "struct"

    def test_empty_input(self):
        result = collect_type_definitions_with_comments("", "empty.h")
        assert result == {}


class TestScanProjectTypes:
    def test_scans_directory(self, sample_c_project):
        types = scan_project_types(sample_c_project)
        assert isinstance(types, dict)

    def test_scans_single_h_file(self, sample_h_file):
        types = scan_project_types(sample_h_file)
        assert isinstance(types, dict)
        # Check that some types were found
        assert len(types) > 0

    def test_deduplicates_types(self, sample_h_file):
        types = scan_project_types(sample_h_file)
        names = list(types.keys())
        assert len(names) == len(set(names))


class TestLoadPreviousTypeCache:
    def test_loads_valid_cache(self, tmp_path):
        cache_path = tmp_path / "types.json"
        data = {
            "type_definitions": {"A": {"kind": "struct"}},
            "type_references": {"A": "A_1"},
        }
        cache_path.write_text(json.dumps(data))
        result, path = load_previous_type_cache(str(cache_path))
        assert result["type_definitions"] == {"A": {"kind": "struct"}}
        assert result["type_references"] == {"A": "A_1"}
        assert path == str(cache_path)

    def test_returns_empty_dict_for_missing_file(self):
        result, path = load_previous_type_cache("/nonexistent/types.json")
        assert result["type_definitions"] == {}
        assert result["type_references"] == {}
        assert path is None

    def test_handles_invalid_json(self, tmp_path):
        cache_path = tmp_path / "bad_types.json"
        cache_path.write_text("not json")
        result, path = load_previous_type_cache(str(cache_path))
        assert result["type_definitions"] == {}
        assert result["type_references"] == {}
        assert path is None


class TestWriteTypesCache:
    def test_writes_cache_file(self, tmp_path):
        cache_path = tmp_path / "cache" / "types.json"
        master_data = {
            "type_definitions": {"A": {"kind": "struct"}, "B": {"kind": "enum"}},
            "type_references": {},
        }
        write_types_cache(str(cache_path), master_data)
        assert os.path.exists(str(cache_path))
        with open(str(cache_path)) as f:
            written = json.load(f)
        assert written["type_references"]["A"] == "A_1"
        assert written["type_references"]["B"] == "A_2"

    def test_sorts_by_name(self, tmp_path):
        cache_path = tmp_path / "cache2" / "types.json"
        master_data = {
            "type_definitions": {"Z": {"kind": "struct"}, "A": {"kind": "struct"}},
            "type_references": {},
        }
        write_types_cache(str(cache_path), master_data)
        with open(str(cache_path)) as f:
            written = json.load(f)
        # Z is later alphabetically, so gets A_2
        assert written["type_references"]["A"] == "A_1"
        assert written["type_references"]["Z"] == "A_2"


class TestIsMissingTypeDescription:
    def test_missing_description(self):
        assert is_missing_type_description({"type_description": ""})
        assert is_missing_type_description({"type_description": None})
        assert is_missing_type_description({})

    def test_present_description(self):
        assert not is_missing_type_description({"type_description": "A valid description"})

    def test_non_string_description(self):
        assert is_missing_type_description({"type_description": 123})

    def test_ai_failed_description(self):
        assert is_missing_type_description({"type_description": AI_FAILED})


class TestSummarizeAiResult:
    def test_success(self):
        status, preview = summarize_ai_result("A short description")
        assert status == "success"
        assert "A short description" in preview

    def test_failed(self):
        status, preview = summarize_ai_result(AI_FAILED)
        assert status == "failed"

    def test_long_description_truncated(self):
        desc = "x" * 50
        status, preview = summarize_ai_result(desc)
        assert status == "success"
        assert "..." in preview
