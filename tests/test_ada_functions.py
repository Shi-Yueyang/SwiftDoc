import os
import pytest

from parsers.ada.functions import (
    extract_parameters,
    extract_return_type,
    extract_return_statements,
    extract_calls_from_body,
    clean_ada_body,
    normalize_ada_code,
    build_global_lookup,
    is_variable_written,
    scan_all_functions,
    _get_subprogram_spec,
)
from parsers.ada._utils import find_ada_identifier
from tree_sitter import Language, Parser
import tree_sitter_ada


ADA_LANGUAGE = Language(tree_sitter_ada.language())
ada_parser = Parser(ADA_LANGUAGE)


def parse_ada_code(code):
    if isinstance(code, str):
        code = bytes(code, "utf8")
    tree = ada_parser.parse(code)
    return tree.root_node


def _find_subprogram_body(root_node, name):
    """Find a subprogram_body node by name (recursively)."""
    def walk(node):
        if node.type == "subprogram_body":
            spec = _get_subprogram_spec(node)
            if spec:
                ident = find_ada_identifier(spec)
                if ident and ident.text.decode("utf-8") == name:
                    return node
        for child in node.children:
            result = walk(child)
            if result:
                return result
        return None
    return walk(root_node)


def _write_ada_file(tmp_dir, filename, content):
    path = os.path.join(tmp_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# ── parameter extraction ────────────────────────────────────────────────────

class TestExtractParameters:
    def test_in_mode_parameter(self):
        code = b"procedure P(X : in Integer) is begin null; end P;"
        root = parse_ada_code(code)
        body = _find_subprogram_body(root, "P")
        spec = _get_subprogram_spec(body)
        params = extract_parameters(spec)
        assert len(params) == 1
        assert params[0]["name"] == "X"
        assert params[0]["type"] == "Integer"
        assert params[0]["direction"] == "in"

    def test_out_mode_parameter(self):
        code = b"procedure P(Y : out Float) is begin null; end P;"
        root = parse_ada_code(code)
        body = _find_subprogram_body(root, "P")
        spec = _get_subprogram_spec(body)
        params = extract_parameters(spec)
        assert len(params) == 1
        assert params[0]["direction"] == "out"

    def test_in_out_mode_parameter(self):
        code = b"procedure P(Z : in out Boolean) is begin null; end P;"
        root = parse_ada_code(code)
        body = _find_subprogram_body(root, "P")
        spec = _get_subprogram_spec(body)
        params = extract_parameters(spec)
        assert params[0]["direction"] == "in out"

    def test_default_mode_is_in(self):
        code = b"procedure P(A : Integer) is begin null; end P;"
        root = parse_ada_code(code)
        body = _find_subprogram_body(root, "P")
        spec = _get_subprogram_spec(body)
        params = extract_parameters(spec)
        assert params[0]["direction"] == "in"

    def test_multiple_parameters(self):
        code = b"procedure P(A, B : in Integer; C : out Float) is begin null; end P;"
        root = parse_ada_code(code)
        body = _find_subprogram_body(root, "P")
        spec = _get_subprogram_spec(body)
        params = extract_parameters(spec)
        assert len(params) == 3
        names = {p["name"] for p in params}
        assert names == {"A", "B", "C"}

    def test_no_parameters(self):
        code = b"procedure No_Params is begin null; end No_Params;"
        root = parse_ada_code(code)
        body = _find_subprogram_body(root, "No_Params")
        spec = _get_subprogram_spec(body)
        params = extract_parameters(spec)
        assert params == []


# ── return type extraction ──────────────────────────────────────────────────

class TestExtractReturnType:
    def test_extracts_function_return_type(self):
        code = b"function Get_Value return Integer is begin return 42; end Get_Value;"
        root = parse_ada_code(code)
        body = _find_subprogram_body(root, "Get_Value")
        spec = _get_subprogram_spec(body)
        ret = extract_return_type(spec)
        assert ret == "Integer"

    def test_no_return_for_procedure(self):
        code = b"procedure Do_Stuff is begin null; end Do_Stuff;"
        root = parse_ada_code(code)
        body = _find_subprogram_body(root, "Do_Stuff")
        spec = _get_subprogram_spec(body)
        ret = extract_return_type(spec)
        assert ret is None


# ── return statement extraction ─────────────────────────────────────────────

class TestExtractReturnStatements:
    def test_extracts_simple_return_with_value(self):
        code = b"function F return Integer is begin return 42; end F;"
        root = parse_ada_code(code)
        body = _find_subprogram_body(root, "F")
        exprs = extract_return_statements(body)
        assert len(exprs) == 1
        assert "42" in exprs[0]

    def test_extracts_bare_return(self):
        code = b"procedure P is begin return; end P;"
        root = parse_ada_code(code)
        body = _find_subprogram_body(root, "P")
        exprs = extract_return_statements(body)
        assert len(exprs) == 1

    def test_multiple_returns(self):
        code = b"""
        function F(X : Integer) return Integer is
        begin
           if X > 0 then return 1; else return 0; end if;
        end F;"""
        root = parse_ada_code(code)
        body = _find_subprogram_body(root, "F")
        exprs = extract_return_statements(body)
        assert len(exprs) == 2


# ── call extraction ─────────────────────────────────────────────────────────

class TestExtractCallsFromBody:
    def test_extracts_procedure_call(self):
        code = b"procedure P is begin Do_Work; end P;"
        root = parse_ada_code(code)
        body = _find_subprogram_body(root, "P")
        calls = extract_calls_from_body(body)
        assert "Do_Work" in calls

    def test_does_not_extract_keywords(self):
        code = b"procedure P is begin null; end P;"
        root = parse_ada_code(code)
        body = _find_subprogram_body(root, "P")
        calls = extract_calls_from_body(body)
        assert calls == []


# ── body cleaning ───────────────────────────────────────────────────────────

class TestCleanAdaBody:
    def test_removes_comments(self):
        body = "X := 1; -- increment\nY := 2;"
        cleaned = clean_ada_body(body)
        assert "--" not in cleaned
        assert "increment" not in cleaned

    def test_handles_empty_body(self):
        assert clean_ada_body("") == ""

    def test_removes_newlines(self):
        body = "X := 1;\nY := 2;\n"
        cleaned = clean_ada_body(body)
        assert "\n" not in cleaned


class TestNormalizeAdaCode:
    def test_removes_all_whitespace(self):
        code = "X := Y + Z;"
        normalized = normalize_ada_code(code)
        assert " " not in normalized

    def test_preserves_string_literals(self):
        code = 'S := "hello world";'
        normalized = normalize_ada_code(code)
        assert "hello world" in normalized

    def test_removes_comments(self):
        code = "X := 1; -- a comment"
        normalized = normalize_ada_code(code)
        assert "acomment" not in normalized


# ── global variable tracking ────────────────────────────────────────────────

class TestBuildGlobalLookup:
    def test_builds_lookup_by_name(self):
        globals_list = [
            {"name": "Counter", "type": "Integer", "file": "test.adb"},
        ]
        lookup = build_global_lookup(globals_list)
        assert "Counter" in lookup
        assert lookup["Counter"]["type"] == "Integer"

    def test_ignores_missing_name(self):
        globals_list = [{"type": "Integer"}]
        lookup = build_global_lookup(globals_list)
        assert len(lookup) == 0


class TestIsVariableWritten:
    def test_detects_write_in_assignment(self):
        code = b"procedure P is begin X := 5; end P;"
        root = parse_ada_code(code)
        # Find the identifier node for X inside the assignment_statement
        def find_assignment(node):
            if node.type == "assignment_statement":
                return node
            for child in node.children:
                r = find_assignment(child)
                if r:
                    return r
            return None
        assign = find_assignment(root)
        # The first named child of assignment_statement should be the target
        for child in assign.children:
            if child.is_named and child.type == "identifier" and child.text.decode("utf-8") == "X":
                assert is_variable_written(child) is True
                return
        pytest.fail("Could not find X identifier in assignment")


# ── scan all functions ──────────────────────────────────────────────────────

class TestScanAllFunctions:
    def test_finds_procedures_in_adb_files(self, tmp_dir):
        code = "procedure Main is begin null; end Main;"
        _write_ada_file(tmp_dir, "main.adb", code)
        result = scan_all_functions(tmp_dir, {"type_references": {}, "type_definitions": {}}, [])
        assert any(f["name"] == "Main" for f in result)

    def test_finds_functions_in_adb_files(self, tmp_dir):
        code = "function Add(A, B : Integer) return Integer is begin return A + B; end Add;"
        _write_ada_file(tmp_dir, "math.adb", code)
        result = scan_all_functions(tmp_dir, {"type_references": {}, "type_definitions": {}}, [])
        assert any(f["name"] == "Add" for f in result)

    def test_resolves_called_by(self, tmp_dir):
        code = """procedure Caller is begin Target; end Caller;
procedure Target is begin null; end Target;"""
        _write_ada_file(tmp_dir, "test.adb", code)
        result = scan_all_functions(tmp_dir, {"type_references": {}, "type_definitions": {}}, [])
        target = next(f for f in result if f["name"] == "Target")
        assert "Caller" in target["called_by"]

    def test_empty_when_no_adb_files(self, tmp_dir):
        result = scan_all_functions(tmp_dir, {"type_references": {}, "type_definitions": {}}, [])
        assert result == []

    def test_each_function_has_required_fields(self, tmp_dir):
        code = "procedure Proc is begin null; end Proc;"
        _write_ada_file(tmp_dir, "test.adb", code)
        result = scan_all_functions(tmp_dir, {"type_references": {}, "type_definitions": {}}, [])
        for f in result:
            assert "name" in f
            assert "file" in f
            assert "inputs" in f
            assert "returns" in f
            assert "calls" in f
            assert "called_by" in f


# ── AI / metadata helpers ───────────────────────────────────────────────────


