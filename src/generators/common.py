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
    if kind == "struct":
        members = info.get("members", [])
        if members:
            members_str = "\n   ".join(members)
            return f"type {type_name} is record\n   {members_str}\nend record;"
        return f"type {type_name} is record\n   null;\nend record;"
    elif kind == "enum":
        values = info.get("values", [])
        if values:
            values_str = ", ".join(values)
            return f"type {type_name} is ({values_str});"
        return f"type {type_name} is (); -- no values"
    elif kind == "typedef":
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


def load_types(types_json: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    if types_json and os.path.exists(types_json):
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
