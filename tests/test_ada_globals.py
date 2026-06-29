import os
import pytest

from parsers.ada.globals import collect_globals_from_ada_file, extract_all_globals


def _write_ada_file(tmp_dir, filename, content):
    path = os.path.join(tmp_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class TestCollectGlobalsFromAdaFile:
    def test_finds_package_level_variable(self, tmp_dir):
        code = "package P is Global_Var : Integer; end P;"
        path = _write_ada_file(tmp_dir, "test.ads", code)
        result = collect_globals_from_ada_file(path)
        names = {v["name"] for v in result}
        assert "Global_Var" in names

    def test_finds_variable_with_default(self, tmp_dir):
        code = "package P is Count : Integer := 0; end P;"
        path = _write_ada_file(tmp_dir, "test.ads", code)
        result = collect_globals_from_ada_file(path)
        assert any(v["name"] == "Count" and v["type"] == "Integer" for v in result)

    def test_skips_variables_inside_subprogram(self, tmp_dir):
        code = """package body P is
           procedure Foo is
              Local : Integer;
           begin
              null;
           end Foo;
        end P;"""
        path = _write_ada_file(tmp_dir, "test.adb", code)
        result = collect_globals_from_ada_file(path)
        names = {v["name"] for v in result}
        assert "Local" not in names

    def test_all_variables_have_required_fields(self, tmp_dir):
        code = "package P is X : Boolean; end P;"
        path = _write_ada_file(tmp_dir, "test.ads", code)
        result = collect_globals_from_ada_file(path)
        for v in result:
            assert "name" in v
            assert "type" in v
            assert "file" in v
            assert "kind" in v
            assert v["kind"] == "definition"
            assert v["is_static"] is False

    def test_finds_variables_in_package_body(self, tmp_dir):
        code = """package body P is
           Internal_Counter : Integer := 0;
        end P;"""
        path = _write_ada_file(tmp_dir, "test.adb", code)
        result = collect_globals_from_ada_file(path)
        assert any(v["name"] == "Internal_Counter" for v in result)

    def test_extracts_correct_type(self, tmp_dir):
        code = "package P is Flag : Boolean := True; end P;"
        path = _write_ada_file(tmp_dir, "test.ads", code)
        result = collect_globals_from_ada_file(path)
        for v in result:
            if v["name"] == "Flag":
                assert v["type"] == "Boolean"

    def test_skips_private_part_variables(self, tmp_dir):
        code = """package P is
           Public_Var : Integer;
        private
           Result : Integer;
        end P;"""
        path = _write_ada_file(tmp_dir, "test.ads", code)
        result = collect_globals_from_ada_file(path)
        names = {v["name"] for v in result}
        assert "Public_Var" in names
        assert "Result" not in names

    def test_body_variable_not_affected_by_private_filter(self, tmp_dir):
        """Private-part filtering is per-node: body variables are never private."""
        code = """package body P is
           Result : Float := 0.0;
        end P;"""
        path = _write_ada_file(tmp_dir, "test.adb", code)
        result = collect_globals_from_ada_file(path)
        names = {v["name"] for v in result}
        assert "Result" in names


class TestExtractAllGlobals:
    def test_extracts_from_directory(self, tmp_dir):
        _write_ada_file(tmp_dir, "pkg.ads", "package P is X : Integer; Y : Float; end P;")
        result = extract_all_globals(tmp_dir)
        assert len(result) >= 2
        names = {r["name"] for r in result}
        assert names >= {"X", "Y"}

    def test_extracts_from_single_file(self, tmp_dir):
        path = _write_ada_file(tmp_dir, "test.ads", "package P is Mode : Integer; end P;")
        result = extract_all_globals(path)
        assert any(r["name"] == "Mode" for r in result)

    def test_returns_list(self, tmp_dir):
        result = extract_all_globals(tmp_dir)
        assert isinstance(result, list)

    def test_deduplicates_by_name(self, tmp_dir):
        code = "package P is X : Integer := 1; end P;"
        _write_ada_file(tmp_dir, "a.ads", code)
        _write_ada_file(tmp_dir, "b.ads", code)
        result = extract_all_globals(tmp_dir)
        names = [r["name"] for r in result]
        assert len(names) == len(set(names))
