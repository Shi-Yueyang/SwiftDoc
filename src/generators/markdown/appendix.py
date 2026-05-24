import os
import re
import json
import logging
from typing import Dict, Any, List, Tuple, Optional, Set


logger = logging.getLogger(__name__)


def remove_c_comments(text: str) -> str:
    """Remove both block /* ... */ and line // ... comments from text."""
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    text = re.sub(r'//.*?(?=\n|$)', '', text, flags=re.MULTILINE)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'[ \t]*\n[ \t]*', '\n', text)
    return text.strip()


def generate_definition(type_name: str, info: Dict[str, Any]) -> str:
    """Generate a C type definition string, replacing newlines with <br>."""
    kind = info.get("kind", "unknown")
    if kind == "struct":
        members = info.get("members", [])
        cleaned_members = [remove_c_comments(m) for m in members if remove_c_comments(m)]
        members_str = "<br>    ".join(cleaned_members) if cleaned_members else "    /* no members */"
        return f"typedef struct {{<br>    {members_str}<br>}} {type_name};"
    elif kind == "union":
        members = info.get("members", [])
        cleaned_members = [remove_c_comments(m) for m in members if remove_c_comments(m)]
        members_str = "<br>    ".join(cleaned_members) if cleaned_members else "    /* no members */"
        return f"typedef union {{<br>    {members_str}<br>}} {type_name};"
    elif kind == "enum":
        values = info.get("values", [])
        cleaned_values = [remove_c_comments(v).strip() for v in values if remove_c_comments(v).strip()]
        if cleaned_values:
            values_str = ",<br>    ".join(cleaned_values)
            enum_body = f"<br>    {values_str}<br>"
        else:
            enum_body = "<br>    /* no values */<br>"
        return f"typedef enum {{{enum_body}}} {type_name};"
    elif kind == "typedef":
        original = info.get("original_type", "")
        original_clean = remove_c_comments(original)
        return f"typedef {original_clean} {type_name};"
    else:
        return f"/* unknown kind: {kind} */ {type_name}"


def generate_appendix_md(types_json_path: str, output_md_path: str, filter_types: Optional[Set[str]] = None) -> None:
    if not os.path.exists(types_json_path):
        logger.warning("Types cache file not found: %s", types_json_path)
        return
    with open(types_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    type_defs = data.get("type_definitions", {})
    type_refs = data.get("type_references", {})

    if not type_defs:
        logger.warning("No type definitions found.")
        return

    rows: List[Tuple[str, str, str, str]] = []
    for type_name, ref in type_refs.items():
        if type_name not in type_defs:
            continue
        if filter_types is not None and type_name not in filter_types:
            continue
        info = type_defs[type_name]
        definition = generate_definition(type_name, info)
        description = info.get("type_description", "").strip()
        if not description:
            description = "No description"
        rows.append((ref, type_name, definition, description))

    def sort_key(row):
        match = re.search(r'A_(\d+)', row[0])
        if match:
            return int(match.group(1))
        return 0
    rows.sort(key=sort_key)

    md_lines = []
    md_lines.append("# Appendix Global Data Structures")
    md_lines.append("")
    md_lines.append("| Reference REF | Identifier | Definition | Description |")
    md_lines.append("|------------|------------|------------|------------|")

    for ref, ident, definition, desc in rows:
        definition_esc = definition.replace('|', '\\|')
        desc_esc = desc.replace('|', '\\|')
        md_lines.append(f"| {ref} | {ident} | {definition_esc} | {desc_esc} |")

    md_lines.append("")
    md_lines.append("---")

    os.makedirs(os.path.dirname(output_md_path), exist_ok=True)
    with open(output_md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md_lines))
    logger.debug("Appendix saved to %s", output_md_path)
