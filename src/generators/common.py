"""Shared utilities for documentation generators.

Both markdown and docx generators import from here to avoid duplication.
"""

import os
import re
import json
from typing import Any


def remove_c_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//.*?(?=\n|$)", "", text, flags=re.MULTILINE)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    return text.strip()


def generate_definition(type_name: str, info: dict[str, Any], language: str = "c") -> str:
    """Generate a type definition string using \\n as line separator."""
    if language == "ada":
        return _generate_ada_definition(type_name, info)
    return _generate_c_definition(type_name, info)


def _generate_c_definition(type_name: str, info: dict[str, Any]) -> str:
    kind = info.get("kind", "unknown")
    if kind == "struct":
        members = info.get("members", [])
        cleaned = [remove_c_comments(m) for m in members if remove_c_comments(m)]
        members_str = "\n    ".join(cleaned) if cleaned else "    /* no members */"
        return f"typedef struct {{\n    {members_str}\n}} {type_name};"
    elif kind == "union":
        members = info.get("members", [])
        cleaned = [remove_c_comments(m) for m in members if remove_c_comments(m)]
        members_str = "\n    ".join(cleaned) if cleaned else "    /* no members */"
        return f"typedef union {{\n    {members_str}\n}} {type_name};"
    elif kind == "enum":
        values = info.get("values", [])
        cleaned = [remove_c_comments(v).strip() for v in values if remove_c_comments(v).strip()]
        if cleaned:
            values_str = ",\n    ".join(cleaned)
            enum_body = f"\n    {values_str}\n"
        else:
            enum_body = "\n    /* no values */\n"
        return f"typedef enum {{{enum_body}}} {type_name};"
    elif kind == "typedef":
        original = info.get("original_type", "")
        original_clean = remove_c_comments(original)
        return f"typedef {original_clean} {type_name};"
    else:
        return f"/* unknown kind: {kind} */ {type_name}"


def _generate_ada_definition(type_name: str, info: dict[str, Any]) -> str:
    kind = info.get("kind", "unknown")
    if kind == "record":
        members = info.get("members", [])
        if members:
            members_str = "\n   ".join(members)
            return f"type {type_name} is record\n   {members_str}\nend record;"
        return f"type {type_name} is record\n   null;\nend record;"
    elif kind == "enumeration":
        values = info.get("values", [])
        if values:
            values_str = ", ".join(values)
            return f"type {type_name} is ({values_str});"
        return f"type {type_name} is (); -- no values"
    elif kind == "subtype":
        original = info.get("original_type", "")
        return f"subtype {type_name} is {original};"
    elif kind in ("access", "array", "derived", "modular", "fixed_point",
                  "decimal_fixed_point", "float", "interface", "private", "type"):
        original = info.get("original_type", "")
        return f"type {type_name} is {original};"
    else:
        return f"-- unknown kind: {kind} {type_name}"


def normalize_function_for_doc(func: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(func)
    normalized.setdefault("algorithm_logic", "")
    normalized.setdefault("module_summary", "")
    normalized.setdefault("return_type", "")
    normalized.setdefault("start_line", 0)
    normalized.setdefault("conditional_macros", [])

    normalized_inputs = []
    for inp in normalized.get("inputs", []):
        if isinstance(inp, dict):
            normalized_input = dict(inp)
            normalized_input.setdefault("inputs_description", "")
            normalized_inputs.append(normalized_input)
    normalized["inputs"] = normalized_inputs

    returns = normalized.get("returns", [])
    if isinstance(returns, list) and returns and isinstance(returns[0], str):
        normalized["returns"] = [
            {"expression": expr, "return_description": ""} for expr in returns
        ]
    else:
        normalized_returns = []
        for ret in returns if isinstance(returns, list) else []:
            if isinstance(ret, dict):
                normalized_return = dict(ret)
                normalized_return.setdefault("expression", "")
                normalized_return.setdefault("return_description", "")
                normalized_returns.append(normalized_return)
        normalized["returns"] = normalized_returns

    return normalized


def load_types(types_json: str | dict | None) -> tuple[dict[str, Any], dict[str, Any]]:
    if types_json is None:
        return {}, {}
    if isinstance(types_json, dict):
        return (
            types_json.get("type_definitions", {}),
            types_json.get("type_references", {}),
        )
    if os.path.exists(types_json):
        with open(types_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (
            data.get("type_definitions", {}),
            data.get("type_references", {}),
        )
    return {}, {}


def build_type_desc_map(type_defs: dict[str, Any]) -> dict[str, str]:
    return {
        tname: info.get("type_description", "")
        for tname, info in type_defs.items()
        if isinstance(info, dict) and info.get("type_description")
    }


def _extract_base_type_name(type_str: str) -> str:
    """Strip C/Ada qualifiers, pointers, and array brackets from a type string.

    Returns the bare type name suitable for looking up in type_refs.
    Examples: "const TaskDesc*" → "TaskDesc", "Point[]" → "Point",
    "struct MyStruct *" → "MyStruct", "BYTE*" → "BYTE".
    """
    _QUALIFIERS = frozenset({
        "const", "volatile", "static", "extern", "unsigned", "signed",
        "struct", "enum", "union",
    })
    parts = type_str.split()
    # Find the first meaningful type-name token
    for part in parts:
        stripped = part.rstrip("*")
        if stripped and stripped not in _QUALIFIERS:
            # Strip array brackets
            base = stripped.split("[")[0]
            return base.strip()
    return type_str.strip()


def build_local_type_refs(
    function_list: list[dict[str, Any]],
    type_refs: dict[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    """Build a per-document local type-reference mapping.

    Scans all function inputs across *function_list* for types that have
    a project-wide reference in *type_refs*, then assigns local A_1, A_2, ...
    codes in sorted-by-name order for deterministic output.

    Returns (local_type_refs, local_ref_to_type) where:
      - local_type_refs: type_name -> "A_N" (for use in rendering)
      - local_ref_to_type: "A_N" -> type_name (for building the local table)
    """
    referenced_types: set[str] = set()
    for func in function_list:
        for inp in func.get("inputs", []):
            base = _extract_base_type_name(inp.get("type", ""))
            if base and base in type_refs:
                referenced_types.add(base)

    sorted_types = sorted(referenced_types)
    local_type_refs: dict[str, str] = {}
    local_ref_to_type: dict[str, str] = {}
    for i, tname in enumerate(sorted_types, start=1):
        code = f"A_{i}"
        local_type_refs[tname] = code
        local_ref_to_type[code] = tname

    return local_type_refs, local_ref_to_type
