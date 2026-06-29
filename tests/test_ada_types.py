import os
import pytest

from parsers.ada.types import (
    collect_ada_types_from_file,
    scan_project_types,
)
from parsers.common import (
    is_missing_type_description,
    summarize_ai_result,
    AI_FAILED,
)


def _write_ada_file(tmp_dir, filename, content):
    path = os.path.join(tmp_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class TestCollectAdaTypes:
    def test_finds_record_type(self, tmp_dir):
        code = "package P is type Point is record X : Integer; Y : Integer; end record; end P;"
        path = _write_ada_file(tmp_dir, "test.ads", code)
        result = collect_ada_types_from_file(path)
        assert "Point" in result
        assert result["Point"]["kind"] == "record"
        assert len(result["Point"]["members"]) == 2

    def test_finds_enumeration_type(self, tmp_dir):
        code = "package P is type Color is (Red, Green, Blue); end P;"
        path = _write_ada_file(tmp_dir, "test.ads", code)
        result = collect_ada_types_from_file(path)
        assert "Color" in result
        assert result["Color"]["kind"] == "enumeration"
        assert result["Color"]["values"] == ["Red", "Green", "Blue"]

    def test_finds_access_type(self, tmp_dir):
        code = "package P is type Int_Ptr is access Integer; end P;"
        path = _write_ada_file(tmp_dir, "test.ads", code)
        result = collect_ada_types_from_file(path)
        assert "Int_Ptr" in result
        assert result["Int_Ptr"]["kind"] == "access"
        assert "access" in result["Int_Ptr"]["original_type"]

    def test_finds_subtype(self, tmp_dir):
        code = "package P is subtype My_Int is Integer range 1 .. 100; end P;"
        path = _write_ada_file(tmp_dir, "test.ads", code)
        result = collect_ada_types_from_file(path)
        assert "My_Int" in result
        assert result["My_Int"]["kind"] == "subtype"
        assert "Integer" in result["My_Int"]["original_type"]

    def test_finds_derived_type(self, tmp_dir):
        code = "package P is type Meters is new Float; end P;"
        path = _write_ada_file(tmp_dir, "test.ads", code)
        result = collect_ada_types_from_file(path)
        assert "Meters" in result
        assert result["Meters"]["kind"] == "derived"

    def test_finds_array_type(self, tmp_dir):
        code = "package P is type Arr is array (1 .. 10) of Integer; end P;"
        path = _write_ada_file(tmp_dir, "test.ads", code)
        result = collect_ada_types_from_file(path)
        assert "Arr" in result
        assert result["Arr"]["kind"] == "array"
        assert "array" in result["Arr"]["original_type"]

    def test_finds_modular_type(self, tmp_dir):
        code = "package P is type Flags is mod 256; end P;"
        path = _write_ada_file(tmp_dir, "test.ads", code)
        result = collect_ada_types_from_file(path)
        assert "Flags" in result
        assert result["Flags"]["kind"] == "modular"
        assert "mod" in result["Flags"]["original_type"]

    def test_finds_fixed_point_type(self, tmp_dir):
        code = "package P is type Fixed is delta 0.1 range 0.0 .. 100.0; end P;"
        path = _write_ada_file(tmp_dir, "test.ads", code)
        result = collect_ada_types_from_file(path)
        assert "Fixed" in result
        assert result["Fixed"]["kind"] == "fixed_point"

    def test_finds_float_type(self, tmp_dir):
        code = "package P is type Real is digits 10; end P;"
        path = _write_ada_file(tmp_dir, "test.ads", code)
        result = collect_ada_types_from_file(path)
        assert "Real" in result
        assert result["Real"]["kind"] == "float"

    def test_finds_interface_type(self, tmp_dir):
        code = "package P is type Shape is interface; end P;"
        path = _write_ada_file(tmp_dir, "test.ads", code)
        result = collect_ada_types_from_file(path)
        assert "Shape" in result
        assert result["Shape"]["kind"] == "interface"

    def test_finds_private_type(self, tmp_dir):
        code = "package P is type Handle is private; end P;"
        path = _write_ada_file(tmp_dir, "test.ads", code)
        result = collect_ada_types_from_file(path)
        assert "Handle" in result
        assert result["Handle"]["kind"] == "private"

    def test_multiple_types_in_file(self, tmp_dir):
        code = """package P is
           type Status is (OK, Error);
           type Data is record
              Value : Integer;
           end record;
        end P;"""
        path = _write_ada_file(tmp_dir, "test.ads", code)
        result = collect_ada_types_from_file(path)
        assert len(result) >= 2
        assert "Status" in result
        assert "Data" in result

    def test_associates_preceding_comment(self, tmp_dir):
        code = """package P is
           -- A simple status type
           type Status is (OK, Error);
        end P;"""
        path = _write_ada_file(tmp_dir, "test.ads", code)
        result = collect_ada_types_from_file(path)
        assert "Status" in result
        assert result["Status"].get("comment") == "A simple status type"


class TestScanProjectTypes:
    def test_scans_ads_files_in_directory(self, tmp_dir):
        code = "package P is type Flag is (On, Off); end P;"
        _write_ada_file(tmp_dir, "flags.ads", code)
        result = scan_project_types(tmp_dir)
        assert "Flag" in result

    def test_returns_empty_for_no_ads_files(self, tmp_dir):
        result = scan_project_types(tmp_dir)
        assert result == {}

    def test_deduplicates_across_files(self, tmp_dir):
        code_a = "package A is type T is (X, Y); end A;"
        code_b = "package B is type T is record A : Integer; end record; end B;"
        _write_ada_file(tmp_dir, "a.ads", code_a)
        _write_ada_file(tmp_dir, "b.ads", code_b)
        result = scan_project_types(tmp_dir)
        assert "T" in result
        # Should keep the non-typedef version
        assert result["T"]["kind"] in ("enumeration", "record")

    def test_dedup_record_beats_access(self, tmp_dir):
        code_a = "package A is type T is access Integer; end A;"
        code_b = "package B is type T is record X : Integer; end record; end B;"
        _write_ada_file(tmp_dir, "a.ads", code_a)
        _write_ada_file(tmp_dir, "b.ads", code_b)
        result = scan_project_types(tmp_dir)
        assert "T" in result
        assert result["T"]["kind"] == "record"


class TestIsMissingTypeDescription:
    def test_missing_when_empty(self):
        assert is_missing_type_description({}) is True

    def test_missing_when_ai_failed(self):
        assert is_missing_type_description({"type_description": AI_FAILED}) is True

    def test_not_missing_when_present(self):
        assert is_missing_type_description({"type_description": "A test type"}) is False


class TestSummarizeAiResult:
    def test_failed(self):
        status, preview = summarize_ai_result(AI_FAILED)
        assert status == "failed"

    def test_success(self):
        status, preview = summarize_ai_result("A brief description")
        assert status == "success"
