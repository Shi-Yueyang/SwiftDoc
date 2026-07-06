import os
import re
import logging
from typing import Dict, Any, List, Tuple, Optional, Set

from generators.common import generate_definition


logger = logging.getLogger(__name__)


def generate_appendix_md(types_data: dict, output_md_path: str, filter_types: Optional[Set[str]] = None, language: str = "c") -> None:
    data = types_data
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
        definition = generate_definition(type_name, info, language=language).replace("\n", "<br>")
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


def generate_local_appendix_md(type_defs, local_ref_to_type, language="c"):
    """Return markdown lines for a local types appendix table.

    Parameters
    ----------
    type_defs : dict[str, dict]
        Project-wide type definitions (allows looking up kind/members/values).
    local_ref_to_type : dict[str, str]
        Mapping from local ref code (e.g. "A_1") to type name.
    language : str
        "c" or "ada" -- controls definition syntax.

    Returns
    -------
    list[str]
        Markdown lines to append to the document.
    """
    md_lines: list[str] = []
    md_lines.append("### Appendix - Local Types Reference")
    md_lines.append("")
    md_lines.append("| Reference REF | Identifier | Definition | Description |")
    md_lines.append("|------------|------------|------------|------------|")

    def sort_key(code: str) -> int:
        match = re.search(r'A_(\d+)', code)
        if match:
            return int(match.group(1))
        return 0

    for code in sorted(local_ref_to_type, key=sort_key):
        tname = local_ref_to_type[code]
        info = type_defs.get(tname, {})
        definition = generate_definition(tname, info, language=language).replace("\n", "<br>")
        description = info.get("type_description", "").strip() or "No description"
        definition_esc = definition.replace("|", "\\|")
        desc_esc = description.replace("|", "\\|")
        md_lines.append(f"| {code} | {tname} | {definition_esc} | {desc_esc} |")

    md_lines.append("")
    return md_lines
