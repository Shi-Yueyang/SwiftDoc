#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate appendix document (Markdown table) from global types JSON.
The table contains: Reference, Identifier, Definition, Description.
"""

import json
import re
import os
import argparse
from typing import Dict, Any, List, Tuple

def generate_definition(type_name: str, info: Dict[str, Any]) -> str:
    """
    Generate a complete C definition string for a given type.
    """
    kind = info.get("kind", "unknown")
    if kind == "struct":
        members = info.get("members", [])
        members_str = "\n    ".join(members) if members else "    /* no members */"
        return f"typedef struct {{\n    {members_str}\n}} {type_name};"
    elif kind == "union":
        members = info.get("members", [])
        members_str = "\n    ".join(members) if members else "    /* no members */"
        return f"typedef union {{\n    {members_str}\n}} {type_name};"
    elif kind == "enum":
        values = info.get("values", [])
        if values:
            # Format each value on a separate line, last value without comma
            values_str = ",\n    ".join(values)
            enum_body = f"\n    {values_str}\n"
        else:
            enum_body = "\n    /* no values */\n"
        return f"typedef enum {{{enum_body}}} {type_name};"
    elif kind == "typedef":
        original = info.get("original_type", "")
        # If original is a struct/union definition without a name, we might need to adjust,
        # but for simplicity we keep as is.
        return f"typedef {original} {type_name};"
    else:
        # fallback: just show kind and name
        return f"/* unknown kind: {kind} */ {type_name}"

def generate_appendix_md(types_json_path: str, output_md_path: str) -> None:
    """
    Read types JSON and produce a Markdown table with columns:
    Reference, Identifier, Definition, Description.
    """
    with open(types_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    type_defs = data.get("type_definitions", {})
    type_refs = data.get("type_references", {})

    if not type_defs:
        print("Warning: No type definitions found.")
        return

    # Prepare rows sorted by reference number (A_1, A_2, ...)
    rows: List[Tuple[str, str, str, str]] = []
    for type_name, ref in type_refs.items():
        if type_name not in type_defs:
            continue   # skip if definition missing (should not happen)
        info = type_defs[type_name]
        definition = generate_definition(type_name, info)
        description = info.get("type_description", "").strip()
        if not description:
            description = "无描述"
        rows.append((ref, type_name, definition, description))

    # Sort by reference number (extract integer from "A_123")
    def sort_key(row):
        match = re.search(r'A_(\d+)', row[0])
        if match:
            return int(match.group(1))
        return 0
    rows.sort(key=sort_key)

    # Prepare Markdown content
    md_lines = []
    md_lines.append("# 附录 全局数据结构")
    md_lines.append("")
    md_lines.append("| 参考 REFERENCE | 标识符 IDENTIFY | 定义 DEFINITION | 描述 DESCRIPTION |")
    md_lines.append("|----------------|------------------|------------------|------------------|")

    for ref, ident, definition, desc in rows:
        # Escape pipe characters in definition and description (rare but safe)
        definition_esc = definition.replace('|', '\\|')
        desc_esc = desc.replace('|', '\\|')
        md_lines.append(f"| {ref} | {ident} | {definition_esc} | {desc_esc} |")

    md_lines.append("")
    md_lines.append("---")

    # Write output
    os.makedirs(os.path.dirname(output_md_path), exist_ok=True)
    with open(output_md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md_lines))

    print(f"Appendix saved to {output_md_path}")

def main():
    parser = argparse.ArgumentParser(description="Generate appendix MD from global types JSON.")
    parser.add_argument("--types-json", default=".analysis/INIT_global_types.json",
                        help="Path to global types JSON file (default: .analysis/INIT_global_types.json)")
    parser.add_argument("--output", "-o", default="MD/appendix.md",
                        help="Output Markdown file path (default: MD/appendix.md)")
    args = parser.parse_args()
    generate_appendix_md(args.types_json, args.output)

if __name__ == "__main__":
    main()