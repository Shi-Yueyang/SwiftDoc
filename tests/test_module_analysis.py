import os
import json
import pytest

from parsers.c.functions import (
    find_parameters,
    find_return_statements,
    extract_calls_from_body,
    clean_function_body,
    normalize_c_code,
    build_global_lookup,
    resolve_global_info,
    _analyze_pointer_directions,
    extract_functions_from_c_file,
)
from parsers.common import (
    load_previous_function_cache,
    write_function_cache,
    prepare_function_metadata,
    is_missing_algorithm_logic,
    summarize_ai_result,
    AI_FAILED,
)
from tree_sitter import Language, Parser
import tree_sitter_c


C_LANGUAGE = Language(tree_sitter_c.language())
parser = Parser(C_LANGUAGE)


def parse_c_code(code):
    """Helper: parse C code and return the root node."""
    tree = parser.parse(bytes(code, "utf8"))
    return tree.root_node


def find_first_function_node(root_node, name):
    """Find the first function_definition node with the given name."""
    stack = [root_node]
    while stack:
        node = stack.pop()
        if node.type == "function_definition":
            declarator = node.child_by_field_name("declarator")
            if declarator:
                from core.utils import find_identifier, get_node_text
                ident = find_identifier(declarator)
                if ident and get_node_text(ident) == name:
                    return node
        for child in node.children:
            stack.append(child)
    return None


class TestFindParameters:
    def test_finds_single_param(self):
        code = "int func(int x) { return x; }"
        root = parse_c_code(code)
        func_node = find_first_function_node(root, "func")
        assert func_node is not None
        declarator = func_node.child_by_field_name("declarator")
        params = find_parameters(declarator)
        assert len(params) == 1
        assert params[0]["name"] == "x"
        assert "int" in params[0]["type"]

    def test_finds_multiple_params(self):
        code = "void process(int a, float b, char* c) { }"
        root = parse_c_code(code)
        func_node = find_first_function_node(root, "process")
        declarator = func_node.child_by_field_name("declarator")
        params = find_parameters(declarator)
        assert len(params) == 3
        assert params[0]["name"] == "a"
        assert params[1]["name"] == "b"
        assert params[2]["name"] == "c"

    def test_no_params(self):
        code = "int get_val(void) { return 42; }"
        root = parse_c_code(code)
        func_node = find_first_function_node(root, "get_val")
        declarator = func_node.child_by_field_name("declarator")
        params = find_parameters(declarator)
        assert params == []


class TestFindReturnStatements:
    def test_finds_single_return(self):
        code = "int get() { return 42; }"
        root = parse_c_code(code)
        func_node = find_first_function_node(root, "get")
        body = func_node.child_by_field_name("body")
        returns = find_return_statements(body)
        assert len(returns) == 1
        assert "42" in returns[0]

    def test_finds_multiple_returns(self):
        code = """
        int choose(int flag) {
            if (flag) { return 1; }
            return 0;
        }
        """
        root = parse_c_code(code)
        func_node = find_first_function_node(root, "choose")
        body = func_node.child_by_field_name("body")
        returns = find_return_statements(body)
        assert len(returns) == 2

    def test_no_return_statement(self):
        code = "void nop() { int x = 1; }"
        root = parse_c_code(code)
        func_node = find_first_function_node(root, "nop")
        body = func_node.child_by_field_name("body")
        returns = find_return_statements(body)
        assert returns == []


class TestExtractCallsFromBody:
    def test_finds_direct_call(self):
        code = "void foo() { bar(); }"
        root = parse_c_code(code)
        func_node = find_first_function_node(root, "foo")
        body = func_node.child_by_field_name("body")
        calls = extract_calls_from_body(body)
        assert "bar" in calls

    def test_finds_multiple_calls(self):
        code = "void foo() { init(); process(); cleanup(); }"
        root = parse_c_code(code)
        func_node = find_first_function_node(root, "foo")
        body = func_node.child_by_field_name("body")
        calls = extract_calls_from_body(body)
        assert "init" in calls
        assert "process" in calls
        assert "cleanup" in calls

    def test_deduplicates_calls(self):
        code = "void foo() { bar(); bar(); }"
        root = parse_c_code(code)
        func_node = find_first_function_node(root, "foo")
        body = func_node.child_by_field_name("body")
        calls = extract_calls_from_body(body)
        assert calls == ["bar"]

    def test_no_calls(self):
        code = "void nop() { int x = 1; }"
        root = parse_c_code(code)
        func_node = find_first_function_node(root, "nop")
        body = func_node.child_by_field_name("body")
        calls = extract_calls_from_body(body)
        assert calls == []


class TestCleanFunctionBody:
    def test_removes_line_comments(self):
        result = clean_function_body("int x = 1; // comment\nreturn x;")
        assert "// comment" not in result
        assert "int x = 1;" in result
        assert "return x;" in result

    def test_removes_block_comments(self):
        result = clean_function_body("int x /* inline */ = 1;")
        assert "/* inline */" not in result
        assert "int x" in result

    def test_removes_tabs(self):
        result = clean_function_body("\tint x = 1;\t")
        assert "\t" not in result

    def test_removes_newlines(self):
        result = clean_function_body("int x = 1;\nreturn x;\n")
        assert "\n" not in result


class TestNormalizeCCode:
    def test_removes_whitespace(self):
        result = normalize_c_code("int x = 1;")
        assert " " not in result
        assert result == "intx=1;"

    def test_removes_comments(self):
        result = normalize_c_code("int x = 1; /* comment */")
        assert "comment" not in result

    def test_preserves_strings(self):
        result = normalize_c_code('char* s = "hello world";')
        assert "hello world" in result

    def test_empty_input(self):
        assert normalize_c_code("") == ""
        assert normalize_c_code(None) == ""

    def test_preserves_char_constants(self):
        result = normalize_c_code("char c = 'a';")
        assert "'a'" in result

    def test_same_code_gives_same_normalization(self):
        a = normalize_c_code("int x = 1;\nint y = 2;")
        b = normalize_c_code("int x=1;int y=2;")
        assert a == b


class TestBuildGlobalLookup:
    def test_builds_lookup_tables(self):
        globals_list = [
            {"name": "g_ext", "file": "/a.c", "is_static": False},
            {"name": "g_st", "file": "/b.c", "is_static": True},
        ]
        lookup = build_global_lookup(globals_list)
        assert "g_ext" in lookup["external"]
        assert ("/b.c", "g_st") in lookup["static"]

    def test_skips_nameless_entries(self):
        globals_list = [
            {"file": "/a.c", "is_static": False},
        ]
        lookup = build_global_lookup(globals_list)
        assert lookup["external"] == {}
        assert lookup["static"] == {}


class TestResolveGlobalInfo:
    def test_resolves_static_first(self):
        g_static = {"name": "x", "type": "int_static", "file": "/a.c"}
        g_external = {"name": "x", "type": "int_ext", "file": "/other.c"}
        lookup = {
            "external": {"x": g_external},
            "static": {("/a.c", "x"): g_static},
        }
        result = resolve_global_info(lookup, "/a.c", "x")
        assert result["type"] == "int_static"

    def test_falls_back_to_external(self):
        g_external = {"name": "x", "type": "int_ext"}
        lookup = {
            "external": {"x": g_external},
            "static": {},
        }
        result = resolve_global_info(lookup, "/a.c", "x")
        assert result["type"] == "int_ext"

    def test_returns_none_when_not_found(self):
        lookup = {"external": {}, "static": {}}
        result = resolve_global_info(lookup, "/a.c", "nonexistent")
        assert result is None


class TestLoadPreviousFunctionCache:
    def test_loads_valid_cache(self, tmp_path):
        cache_path = tmp_path / "functions.json"
        data = {"functions": [{"name": "foo"}]}
        cache_path.write_text(json.dumps(data))
        result, path = load_previous_function_cache(str(cache_path))
        assert len(result["functions"]) == 1
        assert result["functions"][0]["name"] == "foo"

    def test_returns_empty_for_missing_file(self):
        result, path = load_previous_function_cache("/nonexistent/funcs.json")
        assert result["functions"] == []
        assert path is None


class TestWriteFunctionCache:
    def test_writes_to_file(self, tmp_path):
        cache_path = tmp_path / "cache" / "functions.json"
        data = {"functions": [{"name": "foo"}]}
        write_function_cache(str(cache_path), data)
        assert os.path.exists(str(cache_path))
        with open(str(cache_path)) as f:
            written = json.load(f)
        assert written["functions"][0]["name"] == "foo"


class TestPrepareFunctionMetadata:
    def test_sets_defaults(self):
        func = {
            "name": "test",
            "returns": ["x + y"],
            "inputs": [{"name": "x", "kind": "parameter", "type": "int"}],
        }
        prepare_function_metadata(func)
        assert func["algorithm_logic"] == ""
        assert func["returns"][0]["return_description"] == ""
        assert func["inputs"][0]["inputs_description"] == ""

    def test_preserves_existing_values(self):
        func = {
            "name": "test",
            "algorithm_logic": "Does stuff.",
            "returns": [{"expression": "0", "return_description": "Success"}],
            "inputs": [{"name": "x", "kind": "parameter", "inputs_description": "Input", "type": "int"}],
        }
        prepare_function_metadata(func)
        assert func["algorithm_logic"] == "Does stuff."
        assert func["returns"][0]["return_description"] == "Success"
        assert func["inputs"][0]["inputs_description"] == "Input"

    def test_adds_type_description_for_globals(self):
        type_descs = {"int": "Integer type"}
        func = {
            "name": "test",
            "returns": [],
            "inputs": [{"name": "g", "kind": "Global variable", "type": "int"}],
        }
        prepare_function_metadata(func, type_descs)
        assert func["inputs"][0]["type_description"] == "Integer type"


class TestIsMissingAlgorithmLogic:
    def test_missing(self):
        assert is_missing_algorithm_logic({"algorithm_logic": ""})
        assert is_missing_algorithm_logic({"algorithm_logic": None})
        assert is_missing_algorithm_logic({})

    def test_present(self):
        assert not is_missing_algorithm_logic({"algorithm_logic": "Does something."})

    def test_ai_failed_logic(self):
        assert is_missing_algorithm_logic({"algorithm_logic": AI_FAILED})


class TestSummarizeAiResult:
    def test_success(self):
        status, preview = summarize_ai_result("Function logic")
        assert status == "success"

    def test_failed(self):
        status, preview = summarize_ai_result(AI_FAILED)
        assert status == "failed"


class TestAnalyzePointerDirections:
    """Tests for _analyze_pointer_directions — detects in/out/in out
    for pointer parameters by analyzing body dereferences."""

    def _get_dirs(self, code, param_names):
        """Parse C code, find the first compound_statement, and run analysis."""
        root = parse_c_code(code)

        def find_body(node):
            if node.type == "compound_statement":
                return node
            for child in node.children:
                result = find_body(child)
                if result:
                    return result
            return None

        body = find_body(root)
        assert body is not None, "No compound_statement found in test code"
        return _analyze_pointer_directions(body, set(param_names))

    def test_read_only_pointer_is_in(self):
        code = """
        void foo(int* p) {
            int x = *p + 1;
        }
        """
        dirs = self._get_dirs(code, ["p"])
        assert dirs["p"] == "in"

    def test_write_only_pointer_is_out(self):
        code = """
        void foo(int* p) {
            *p = 42;
        }
        """
        dirs = self._get_dirs(code, ["p"])
        assert dirs["p"] == "out"

    def test_compound_assign_is_out(self):
        code = """
        void foo(int* p) {
            *p += 5;
        }
        """
        dirs = self._get_dirs(code, ["p"])
        assert dirs["p"] == "out"

    def test_read_and_write_is_in_out(self):
        code = """
        void foo(int* p) {
            int x = *p;
            *p = x + 1;
        }
        """
        dirs = self._get_dirs(code, ["p"])
        assert dirs["p"] == "in out"

    def test_mixed_read_and_compound_write_is_in_out(self):
        code = """
        void foo(int* p) {
            int x = *p + 3;
            *p += 4;
        }
        """
        dirs = self._get_dirs(code, ["p"])
        assert dirs["p"] == "in out"

    def test_increment_decrement_is_in_out(self):
        code = """
        void foo(int* p) {
            ++*p;
        }
        """
        dirs = self._get_dirs(code, ["p"])
        assert dirs["p"] == "in out"

    def test_multiple_pointer_params(self):
        code = """
        void hello(int* input, int* output, int* mixed) {
            int temp = *input + 3 + *mixed;
            *output += 2;
            *mixed += 4;
        }
        """
        dirs = self._get_dirs(code, ["input", "output", "mixed"])
        assert dirs["input"] == "in"
        assert dirs["output"] == "out"
        assert dirs["mixed"] == "in out"

    def test_non_pointer_params_are_ignored(self):
        """Only pointer params are analyzed; non-pointers never appear."""
        dirs = _analyze_pointer_directions(
            parse_c_code("int add(int a, int b) { return a + b; }"),
            set(),
        )
        assert dirs == {}

    def test_empty_body(self):
        dirs = _analyze_pointer_directions(None, {"p"})
        assert dirs["p"] == "in"


_EMPTY_LOOKUP = {"external": {}, "static": {}}


class TestExtractFunctionsFromCFile:
    """Tests for extract_functions_from_c_file — the main per-file extraction."""

    def test_finds_function_inside_ifdef(self, tmp_dir):
        """Regression: functions inside #ifdef should not be skipped."""
        code = """
        #ifdef XYZ
        void guarded_func(void) {
        }
        #endif
        """
        path = os.path.join(tmp_dir, "test_ifdef.c")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        funcs = extract_functions_from_c_file(path, {}, _EMPTY_LOOKUP)
        names = [f["name"] for f in funcs]
        assert "guarded_func" in names, f"Function inside #ifdef not found, got: {names}"

    def test_finds_function_inside_if(self, tmp_dir):
        """Regression: functions inside #if should not be skipped."""
        code = """
        #if 1
        void enabled_func(void) { }
        #endif
        """
        path = os.path.join(tmp_dir, "test_if.c")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        funcs = extract_functions_from_c_file(path, {}, _EMPTY_LOOKUP)
        names = [f["name"] for f in funcs]
        assert "enabled_func" in names, f"Function inside #if not found, got: {names}"

    def test_pointer_direction_in_output(self, tmp_dir):
        """End-to-end: pointer param directions are set in extracted functions."""
        code = """
        void process(int* in_only, int* out_only, int* in_out) {
            int x = *in_only + *in_out;
            *out_only = 42;
            *in_out += 1;
        }
        """
        path = os.path.join(tmp_dir, "test_dirs.c")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        funcs = extract_functions_from_c_file(path, {}, _EMPTY_LOOKUP)
        assert len(funcs) == 1
        f = funcs[0]
        dirs = {inp["name"]: inp["direction"] for inp in f["inputs"]}
        assert dirs["in_only"] == "in"
        assert dirs["out_only"] == "out"
        assert dirs["in_out"] == "in out"

    def test_pointer_type_includes_star(self, tmp_dir):
        """Regression: pointer types should include '*', e.g. 'int*' not 'int'."""
        code = "void foo(int* p) { *p = 0; }"
        path = os.path.join(tmp_dir, "test_type.c")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        funcs = extract_functions_from_c_file(path, {}, _EMPTY_LOOKUP)
        assert len(funcs) == 1
        types = {inp["name"]: inp["type"] for inp in funcs[0]["inputs"]}
        assert "*" in types["p"], f"Expected pointer type with '*', got: {types['p']}"

    def test_finds_top_level_function(self, tmp_dir):
        """Non-preprocessor-guarded functions are still found."""
        code = "void normal(void) { }"
        path = os.path.join(tmp_dir, "test_normal.c")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        funcs = extract_functions_from_c_file(path, {}, _EMPTY_LOOKUP)
        names = [f["name"] for f in funcs]
        assert "normal" in names

    def test_return_type_void(self, tmp_dir):
        code = "void foo(void) { }"
        path = os.path.join(tmp_dir, "test_rt_void.c")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        funcs = extract_functions_from_c_file(path, {}, _EMPTY_LOOKUP)
        assert funcs[0]["return_type"] == "void"

    def test_return_type_int(self, tmp_dir):
        code = "int bar(int x) { return x; }"
        path = os.path.join(tmp_dir, "test_rt_int.c")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        funcs = extract_functions_from_c_file(path, {}, _EMPTY_LOOKUP)
        assert funcs[0]["return_type"] == "int"

    def test_return_type_pointer(self, tmp_dir):
        code = "int* baz(void) { return 0; }"
        path = os.path.join(tmp_dir, "test_rt_ptr.c")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        funcs = extract_functions_from_c_file(path, {}, _EMPTY_LOOKUP)
        assert funcs[0]["return_type"] == "int*"
