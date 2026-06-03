"""
Extract Ada subprogram definitions (procedures/functions) using tree-sitter.

Handles parameter extraction with Ada's in/out/in out modes, function return types,
call extraction, global variable tracking, and nested subprograms.
"""

import os
import re
import json
import logging

import tree_sitter_ada
from tree_sitter import Language, Parser

from core.utils import get_node_text, decode_file, highlight_message, collect_source_files
from parsers.ada._utils import find_ada_identifier
from parsers.common import (
    load_previous_function_cache,
    write_function_cache,
    prepare_function_metadata,
    enrich_function_with_ai,
    summarize_ai_result,
    is_missing_algorithm_logic,
    refresh_functions,
)

logger = logging.getLogger(__name__)

ADA_LANGUAGE = Language(tree_sitter_ada.language())
ada_parser = Parser(ADA_LANGUAGE)


# ── helpers ──────────────────────────────────────────────────────────────────

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
            type_id = find_ada_identifier(child)
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

        name_id = find_ada_identifier(spec_node)
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


def scan_all_functions(project_dir, types_data, global_vars, ignore_calls=None):
    """Scan .adb files and return a list of function dicts (no cache I/O)."""
    adb_files = collect_source_files(project_dir, (".adb",))
    if not adb_files:
        logger.debug("No .adb files found in %s", project_dir)
        return []

    type_refs = types_data.get("type_references", {})
    global_lookup = build_global_lookup(global_vars)
    all_functions = []
    ignored = set(ignore_calls or [])

    for f in adb_files:
        funcs = extract_subprograms_from_file(f, type_refs, global_lookup)
        all_functions.extend(funcs)

    # Resolve called_by
    known_names = {f["name"] for f in all_functions}

    # Filter false positives from bare selected_component calls (field accesses)
    # and explicitly ignored calls
    for func in all_functions:
        func["calls"] = [c for c in func.get("calls", [])
                         if c in known_names and c not in ignored]

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
