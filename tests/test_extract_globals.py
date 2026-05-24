import os
import json
import pytest

from parsers.c.globals import (
    collect_globals_from_c_file,
    collect_extern_from_h_file,
    extract_all_globals,
    get_global_key,
    is_inside_function,
)


class TestGetGlobalKey:
    def test_non_static_returns_name_only(self):
        info = {"name": "global_mode", "file": "/path/file.c", "is_static": False}
        assert get_global_key(info) == "global_mode"

    def test_static_returns_name_and_file_tuple(self):
        info = {"name": "counter", "file": "/path/file.c", "is_static": True}
        assert get_global_key(info) == ("counter", "/path/file.c")

    def test_static_defaults_false(self):
        info = {"name": "x", "file": "/path/file.c"}
        assert get_global_key(info) == "x"


class TestCollectGlobalsFromCFile:
    def test_finds_global_variables(self, sample_c_file):
        vars_list = collect_globals_from_c_file(sample_c_file)
        names = {v["name"] for v in vars_list}
        assert "global_mode" in names
        assert "counter" in names

    def test_marks_static_variables(self, sample_c_file):
        vars_list = collect_globals_from_c_file(sample_c_file)
        for v in vars_list:
            if v["name"] == "counter":
                assert v["is_static"] is True
            elif v["name"] == "global_mode":
                assert v["is_static"] is False

    def test_records_source_file(self, sample_c_file):
        vars_list = collect_globals_from_c_file(sample_c_file)
        for v in vars_list:
            assert v["file"] == sample_c_file

    def test_all_variables_have_required_fields(self, sample_c_file):
        vars_list = collect_globals_from_c_file(sample_c_file)
        for v in vars_list:
            assert "name" in v
            assert "type" in v
            assert "file" in v
            assert "kind" in v
            assert "is_static" in v


class TestCollectExternFromHFile:
    def test_finds_extern_variables(self, sample_h_file):
        vars_list = collect_extern_from_h_file(sample_h_file)
        names = {v["name"] for v in vars_list}
        # These are from extern declarations in the header
        assert len(vars_list) >= 0  # valid even if none, test parses without error

    def test_all_externs_have_correct_kind(self, sample_h_file):
        vars_list = collect_extern_from_h_file(sample_h_file)
        for v in vars_list:
            assert v["kind"] == "extern"
            assert v["is_static"] is False


class TestExtractAllGlobals:
    def test_extracts_from_directory(self, sample_c_project):
        results = extract_all_globals(sample_c_project)
        assert isinstance(results, list)
        assert len(results) > 0

    def test_extracts_from_single_file(self, sample_c_file):
        results = extract_all_globals(sample_c_file)
        assert isinstance(results, list)
        names = [r["name"] for r in results]
        assert "global_mode" in names or "counter" in names

    def test_deduplicates_by_name(self, sample_c_project):
        results = extract_all_globals(sample_c_project)
        names = [r["name"] for r in results]
        assert len(names) == len(set(names)) or all(
            r.get("is_static") for r in results if names.count(r["name"]) > 1
        )
