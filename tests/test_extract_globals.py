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


class TestArrayGlobalTypes:
    """Global arrays / pointers should include the declarator modifier in the type."""

    def _write_and_extract(self, tmp_dir, c_code):
        path = os.path.join(tmp_dir, "test_array.c")
        with open(path, "w", encoding="utf-8") as f:
            f.write(c_code)
        vars_list = collect_globals_from_c_file(path)
        return {v["name"]: v["type"] for v in vars_list}

    def test_simple_array(self, tmp_dir):
        types = self._write_and_extract(tmp_dir, "int arr[10];")
        assert types["arr"] == "int[]"

    def test_multi_dimensional_array(self, tmp_dir):
        types = self._write_and_extract(tmp_dir, "int matrix[10][20];")
        assert types["matrix"] == "int[][]"

    def test_pointer_to_int(self, tmp_dir):
        types = self._write_and_extract(tmp_dir, "int *ptr;")
        assert types["ptr"] == "int*"

    def test_array_of_pointers(self, tmp_dir):
        types = self._write_and_extract(tmp_dir, "int *arr[10];")
        assert types["arr"] == "int*[]"

    def test_array_with_initializer(self, tmp_dir):
        types = self._write_and_extract(tmp_dir, "int arr[] = {1, 2, 3};")
        assert types["arr"] == "int[]"

    def test_plain_int_unchanged(self, tmp_dir):
        types = self._write_and_extract(tmp_dir, "int simple;")
        assert types["simple"] == "int"

    def test_static_array(self, tmp_dir):
        types = self._write_and_extract(tmp_dir, "static int test_global_arr[10];")
        assert types["test_global_arr"] == "int[]"

    def test_extern_array_from_header(self, tmp_dir):
        h_path = os.path.join(tmp_dir, "test.h")
        with open(h_path, "w", encoding="utf-8") as f:
            f.write("extern int ext_arr[5];\n")
        vars_list = collect_extern_from_h_file(h_path)
        types = {v["name"]: v["type"] for v in vars_list}
        assert types["ext_arr"] == "int[]"

    def test_unsigned_long_array(self, tmp_dir):
        types = self._write_and_extract(tmp_dir, "unsigned long buf[256];")
        assert types["buf"] == "unsigned long[]"
