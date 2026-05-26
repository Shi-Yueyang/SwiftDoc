import os
import re
import json
import logging
from typing import Dict, Any, List, Tuple, Optional, Set

from generators.common import remove_c_comments, generate_definition


logger = logging.getLogger(__name__)


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
        definition = generate_definition(type_name, info).replace("\n", "<br>")
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
