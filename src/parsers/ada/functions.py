"""
Extract Ada subprogram definitions (procedures/functions) using tree-sitter.

Handles parameter extraction with Ada's in/out/in out modes, function return types,
call extraction, global variable tracking, and nested subprograms.
"""

import os
import re
import json
import time
import logging
import tempfile
import copy

import tree_sitter_ada
from tree_sitter import Language, Parser

from core.utils import get_node_text, decode_file, highlight_message, collect_source_files
from core.ai import ai_prompt_for_function, call_ai_from_config, AI_FAILED
from core.compare import compare_functions

logger = logging.getLogger(__name__)
AI_RESULT_PREVIEW_CHARS = 24

ADA_LANGUAGE = Language(tree_sitter_ada.language())
ada_parser = Parser(ADA_LANGUAGE)


# ── helpers ──────────────────────────────────────────────────────────────────

def _find_identifier(node):
    for child in node.children:
        if child.is_named and child.type == "identifier":
            return child
    return None


def _find_child_by_type(node, child_type):
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _get_subprogram_spec(body_node):
    """Return the procedure_specification or function_specification child."""
    for child in body_node.children:
        if child.type in ("procedure_specification", "function_specification"):
            return child
    return None


def _is_function(spec_node):
    return spec_node.type == "function_specification"


# ── parameter extraction ─────────────────────────────────────────────────────

def extract_parameters(spec_node):
    """Extract parameters from a procedure/function specification.

    Returns list of dicts with name, type, and direction.
    """
    params = []
    formal_part = None
    for child in spec_node.children:
        if child.type == "formal_part":
            formal_part = child
            break

    if formal_part is None:
        return params

    for child in formal_part.children:
        if child.type != "parameter_specification":
            continue

        # Collect identifiers (parameter names) and type
        identifiers = []
        type_name = None
        mode = "in"  # Ada default is 'in'

        for sub in child.children:
            if sub.is_named and sub.type == "identifier":
                id_text = get_node_text(sub)
                identifiers.append(id_text)
            elif sub.type == "non_empty_mode":
                mode = get_node_text(sub).strip()

        # The last identifier is the type, the rest are parameter names
        if len(identifiers) >= 2:
            type_name = identifiers[-1]
            param_names = identifiers[:-1]
        elif len(identifiers) == 1:
            type_name = identifiers[0]
            param_names = [type_name]
            # This shouldn't happen for proper param specs, but be safe
        else:
            continue

        for pname in param_names:
            params.append({"name": pname, "type": type_name, "direction": mode})

    return params


# ── return type extraction ──────────────────────────────────────────────────

def extract_return_type(spec_node):
    """Extract the return type from a function_specification."""
    for child in spec_node.children:
        if child.type == "result_profile":
            type_id = _find_identifier(child)
            if type_id:
                return get_node_text(type_id)
    return None


# ── body extraction ─────────────────────────────────────────────────────────

def get_subprogram_body_text(body_node):
    """Extract the executable body (statements) of a subprogram."""
    for child in body_node.children:
        if child.type == "handled_sequence_of_statements":
            return get_node_text(child).strip()
    return ""


def clean_ada_body(body_code):
    """Remove Ada comments (--) and collapse whitespace."""
    if not body_code:
        return ""
    body_code = re.sub(r"--.*", "", body_code)
    body_code = body_code.replace("\t", "").replace("\n", "").strip()
    return body_code


def normalize_ada_code(code):
    """Strip all whitespace and comments for diff comparison."""
    if not code:
        return ""
    # Remove Ada comments
    code = re.sub(r"--.*", "", code)
    # Protect string literals
    placeholders = []

    def repl(match):
        placeholders.append(match.group(0))
        return f"\x00STR{len(placeholders)-1}\x00"

    code = re.sub(r'"(?:\\.|[^"\\])*"', repl, code)
    # Remove all whitespace
    code = re.sub(r"\s+", "", code)
    # Restore strings
    for i, s in enumerate(placeholders):
        code = code.replace(f"\x00STR{i}\x00", s)
    return code


# ── return statement extraction ─────────────────────────────────────────────

def extract_return_statements(body_node):
    """Find all simple_return_statement nodes and extract expressions."""
    returns = []
    if body_node is None:
        return returns

    def walk(node):
        if node.type == "simple_return_statement":
            expr_text = get_node_text(node)
            expr = expr_text.replace("return", "").strip()
            if expr.endswith(";"):
                expr = expr[:-1].strip()
            returns.append(expr)
        for child in node.children:
            walk(child)

    walk(body_node)
    return returns


# ── call extraction ─────────────────────────────────────────────────────────

def _get_call_name(node):
    """Get the function name from a call node, handling selected_component."""
    for child in node.children:
        if child.is_named:
            if child.type == "selected_component":
                idents = [c for c in child.children if c.is_named and c.type == "identifier"]
                if idents:
                    return get_node_text(idents[-1])
            elif child.type == "identifier":
                return get_node_text(child)
    return None


def extract_calls_from_body(body_node):
    """Extract function/procedure calls from a subprogram body.

    Handles three Ada call forms:
    - procedure_call_statement: standalone call like `Do_Work;` or `Do_Work(X);`
    - function_call: call with parens in an expression like `Pkg.Func(Y)`
    - bare selected_component: parameterless call like `Pkg.Func` (no parens)
    """
    called = set()
    if body_node is None:
        return []

    def walk(node):
        if node.type == "procedure_call_statement":
            name = _get_call_name(node)
            if name:
                called.add(name)
        elif node.type == "function_call":
            name = _get_call_name(node)
            if name:
                called.add(name)
        elif node.type == "selected_component":
            # Parameterless function call (e.g. `Pkg.Func` without parens).
            # False positives (field accesses like `Rec.Field`) are harmless
            # because called_by resolution filters against known function names.
            if node.parent and node.parent.type != "function_call":
                idents = [c for c in node.children if c.is_named and c.type == "identifier"]
                if len(idents) >= 2:
                    called.add(get_node_text(idents[-1]))
        for child in node.children:
            walk(child)

    walk(body_node)
    return list(called)


# ── global variable tracking ────────────────────────────────────────────────

def build_global_lookup(globals_list):
    """Build a name->info lookup for package-level variables."""
    lookup = {}
    for g in globals_list:
        name = g.get("name")
        if name:
            lookup[name] = g
    return lookup


def is_variable_written(node):
    """Check if an identifier node is the target of an assignment."""
    parent = node.parent
    if parent is None:
        return False
    if parent.type == "assignment_statement":
        # Check if this identifier is on the LHS
        for child in parent.children:
            if child.is_named:
                if child == node or (child.type == "identifier" and child == node):
                    return True
                break
    return False


# ── main extraction ─────────────────────────────────────────────────────────

def _iter_subprogram_bodies(root_node):
    """Yield all subprogram_body nodes at any nesting level."""
    def walk(node):
        if node.type == "subprogram_body":
            yield node
        for child in node.children:
            yield from walk(child)
    yield from walk(root_node)


def extract_subprograms_from_file(file_path, type_refs, global_lookup):
    """Parse a single Ada file and return FuncDef dicts for all subprograms."""
    with open(file_path, "rb") as f:
        raw = f.read()
    text = decode_file(raw)
    tree = ada_parser.parse(bytes(text, "utf8"))
    root_node = tree.root_node

    functions = []

    for body_node in _iter_subprogram_bodies(root_node):
        spec_node = _get_subprogram_spec(body_node)
        if spec_node is None:
            continue

        name_id = _find_identifier(spec_node)
        if name_id is None:
            continue
        func_name = get_node_text(name_id)

        # Parameters
        params = extract_parameters(spec_node)
        inputs = []
        for p in params:
            type_ref = type_refs.get(p["type"], "")
            inputs.append({
                "name": p["name"],
                "kind": "parameter",
                "direction": p["direction"],
                "type": p["type"],
                "type_ref": type_ref,
            })

        # Return type
        returns = []
        if _is_function(spec_node):
            ret_type = extract_return_type(spec_node)
            if ret_type:
                returns = [{"expression": ret_type, "return_description": ""}]

        # Body text
        body_code = get_subprogram_body_text(body_node)
        normalized_body = normalize_ada_code(body_code) if body_code else ""

        # Return statements within body
        return_exprs = extract_return_statements(body_node)

        # Calls
        calls = extract_calls_from_body(body_node)

        # Global variable references
        if global_lookup:
            global_read = set()
            global_written = set()
            referenced = {}

            def find_identifiers(node):
                if node.type == "identifier":
                    name = get_node_text(node)
                    ginfo = global_lookup.get(name)
                    if ginfo is not None:
                        referenced[name] = ginfo
                        if is_variable_written(node):
                            global_written.add(name)
                        else:
                            global_read.add(name)
                for child in node.children:
                    find_identifiers(child)

            find_identifiers(body_node)

            for gname in global_read | global_written:
                ginfo = referenced[gname]
                gtype = ginfo["type"]
                direction = "in out" if gname in global_written else "in"
                type_ref = type_refs.get(gtype, "")
                inputs.append({
                    "name": gname,
                    "kind": "Global variable",
                    "direction": direction,
                    "type": gtype,
                    "type_ref": type_ref,
                })

        functions.append({
            "name": func_name,
            "file": file_path,
            "inputs": inputs,
            "returns": return_exprs,
            "body_code": clean_ada_body(body_code),
            "normalized_body": normalized_body,
            "calls": calls,
        })

    return functions


def scan_all_functions(project_dir, types_data, global_vars):
    """Scan .adb files and return a list of function dicts (no cache I/O)."""
    adb_files = collect_source_files(project_dir, (".adb",))
    if not adb_files:
        logger.debug("No .adb files found in %s", project_dir)
        return []

    type_refs = types_data.get("type_references", {})
    global_lookup = build_global_lookup(global_vars)
    all_functions = []

    for f in adb_files:
        funcs = extract_subprograms_from_file(f, type_refs, global_lookup)
        all_functions.extend(funcs)

    # Resolve called_by
    known_names = {f["name"] for f in all_functions}

    # Filter false positives from bare selected_component calls (field accesses)
    for func in all_functions:
        func["calls"] = [c for c in func.get("calls", []) if c in known_names]

    called_by_map = {}
    for func in all_functions:
        for callee in func.get("calls", []):
            if callee in known_names:
                called_by_map.setdefault(callee, []).append(func["name"])
    for callee, callers in called_by_map.items():
        called_by_map[callee] = list(set(callers))
    for func in all_functions:
        func["called_by"] = called_by_map.get(func["name"], [])

    return all_functions


# ── cache / refresh / AI (reused pattern from C parser) ─────────────────────

def load_previous_function_cache(output_json_path):
    if os.path.exists(output_json_path):
        try:
            with open(output_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("functions", [])
            return data, output_json_path
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to load previous function cache from %s", output_json_path)
    return {"functions": []}, None


def write_function_cache(output_json_path, output_data):
    os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=os.path.dirname(output_json_path), delete=False
    ) as tmp_file:
        json.dump(output_data, tmp_file, indent=2, ensure_ascii=False)
        tmp_path = tmp_file.name
    os.replace(tmp_path, output_json_path)


def prepare_function_metadata(func, type_descriptions=None):
    func["algorithm_logic"] = func.get("algorithm_logic", "")

    if isinstance(func.get("returns"), list) and func["returns"] and isinstance(func["returns"][0], str):
        func["returns"] = [{"expression": expr, "return_description": ""} for expr in func["returns"]]
    else:
        for ret in func.get("returns", []):
            ret["return_description"] = ret.get("return_description", "")

    for inp in func.get("inputs", []):
        inp["inputs_description"] = inp.get("inputs_description", "")
        if inp.get("kind") == "Global variable":
            base_type_match = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", inp["type"])
            base_type = base_type_match.group(1) if base_type_match else inp["type"]
            inp["type_description"] = (type_descriptions or {}).get(base_type, "")


def enrich_function_with_ai(func, type_descriptions):
    prepare_function_metadata(func, type_descriptions)
    prompt = ai_prompt_for_function(func)
    response = call_ai_from_config(prompt)
    if response != AI_FAILED:
        try:
            desc = json.loads(response)
            func["algorithm_logic"] = desc.get("algorithm_logic", "")
            param_descs = {
                item["name"]: item.get("inputs_description", "")
                for item in desc.get("inputs_description", [])
            }
            for inp in func.get("inputs", []):
                inp["inputs_description"] = param_descs.get(inp["name"], inp.get("inputs_description", ""))
            return_descs = desc.get("return_values", [])
            for idx, ret_item in enumerate(func.get("returns", [])):
                ret_item["return_description"] = return_descs[idx] if idx < len(return_descs) else ""
        except json.JSONDecodeError as exc:
            logger.debug("JSON parse failed: %s", exc)
            func["algorithm_logic"] = AI_FAILED
    else:
        func["algorithm_logic"] = AI_FAILED
    return func["algorithm_logic"]


def summarize_ai_result(description):
    normalized = " ".join(str(description).split())
    success = normalized != AI_FAILED
    preview = normalized[:AI_RESULT_PREVIEW_CHARS]
    if len(normalized) > AI_RESULT_PREVIEW_CHARS:
        preview = f"{preview}..."
    return "success" if success else "failed", preview


def is_missing_algorithm_logic(func):
    logic = func.get("algorithm_logic")
    if not isinstance(logic, str) or not logic.strip():
        return True
    return logic == AI_FAILED


def refresh_functions(all_functions, output_json_path, types_data, enable_ai=True):
    type_descriptions = {
        name: info["type_description"]
        for name, info in types_data.get("type_definitions", {}).items()
        if isinstance(info, dict) and "type_description" in info
    }
    previous_data, loaded_from = load_previous_function_cache(output_json_path)
    previous_functions = previous_data.get("functions", [])

    def _func_key(f):
        return (f["name"], f["file"])

    diff = compare_functions(previous_functions, all_functions)

    added = diff.get("added", [])
    modified = diff.get("modified", [])
    removed = diff.get("removed", [])
    changed_functions = [*added, *(item["new"] for item in modified)]

    if enable_ai:
        missing_logic_keys = {
            _func_key(func)
            for func in previous_functions
            if is_missing_algorithm_logic(func)
        }
        changed_map = {_func_key(f): f for f in changed_functions}
        for func in all_functions:
            if _func_key(func) in missing_logic_keys:
                changed_map[_func_key(func)] = func
        changed_functions = list(changed_map.values())

    output_data = {"functions": copy.deepcopy(previous_functions)}
    function_map = {_func_key(f): f for f in output_data["functions"]}

    for func in removed:
        key = _func_key(func)
        if key in function_map:
            del function_map[key]

    for func in changed_functions:
        fresh_function = copy.deepcopy(func)
        if not enable_ai:
            fresh_function["algorithm_logic"] = ""
        prepare_function_metadata(fresh_function, type_descriptions)
        function_map[_func_key(fresh_function)] = fresh_function

    should_persist = bool(
        changed_functions or removed or loaded_from != output_json_path
        or not os.path.exists(output_json_path)
    )

    if enable_ai:
        if changed_functions:
            logger.info(highlight_message("Refreshing AI descriptions for %s changed functions"), len(changed_functions))
        else:
            logger.info(highlight_message("No functions require AI refresh"))
        for idx, func in enumerate(changed_functions, start=1):
            current = function_map[_func_key(func)]
            description = enrich_function_with_ai(current, type_descriptions)
            status, preview = summarize_ai_result(description)
            logger.info("AI progress %s/%s: %s [%s] %s", idx, len(changed_functions), current["name"], status, preview)
            output_data["functions"] = list(function_map.values())
            write_function_cache(output_json_path, output_data)
            time.sleep(0.5)
    elif should_persist:
        output_data["functions"] = list(function_map.values())
        write_function_cache(output_json_path, output_data)

    if enable_ai and not changed_functions and should_persist:
        output_data["functions"] = list(function_map.values())
        write_function_cache(output_json_path, output_data)

    return output_json_path
