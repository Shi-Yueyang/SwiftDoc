"""
Extract type definitions (structs, unions, enums, typedefs) from all .h files in the specified folder,
exclude commented-out types, associate the preceding comments, and output a JSON file with the numbering format A_1, A_2, ...
"""

import os
import re
import json
import logging
from core.utils import decode_file, highlight_message, collect_source_files
from parsers.common import (
    load_previous_type_cache,
    write_types_cache,
    enrich_type_definition,
    summarize_ai_result,
    is_missing_type_description,
    refresh_type_definitions,
)

logger = logging.getLogger(__name__)


def scan_project_types(project_dir):
    h_files = collect_source_files(project_dir, (".h",))
    all_types = {}
    for hf in h_files:
        with open(hf, "rb") as f:
            raw = f.read()
        text = decode_file(raw)
        all_types.update(collect_type_definitions_with_comments(text, hf))

    unique_types = {}
    for name, defn in all_types.items():
        if name not in unique_types:
            unique_types[name] = defn
            continue

        existing = unique_types[name]
        if existing.get("kind") == "typedef" and defn.get("kind") != "typedef":
            unique_types[name] = defn
            logger.debug("Replacing typedef %s with %s", name, defn["kind"])
        else:
            logger.warning("Duplicate type definition '%s' ignored", name)

    return unique_types


def collect_type_definitions_with_comments(header_text, source_file):
    """
    Extract valid type definitions (not inside comments) and associate preceding comments.
    Supported patterns:
    typedef enum [tag] { ... } Name;
    typedef struct [tag] { ... } Name;
    typedef union [tag] { ... } Name;
    typedef Type Alias; (Simple type)
    typedef Type Alias[Size]; (Array type)
    Type names must start with an uppercase or lowercase letter.

    """
    comment_spans = []
    for match in re.finditer(r"/\*.*?\*/", header_text, re.DOTALL):
        comment_spans.append((match.start(), match.end(), match.group(0)))
    for match in re.finditer(r"//.*?(?=\n|$)", header_text):
        comment_spans.append((match.start(), match.end(), match.group(0)))
    comment_spans.sort(key=lambda x: x[0])

    def is_in_comment(pos):
        for cs, ce, _ in comment_spans:
            if cs <= pos < ce:
                return True
        return False

    type_defs = {}
    matches = []

    patterns = [
        # 1. typedef enum [tag] { ... } Name;
        (
            r"typedef\s+enum\s+(?:\w+\s+)?\{([^}]*)\}\s*([A-Za-z][A-Za-z0-9_]*)\s*;",
            "enum",
        ),
        # 2. typedef struct [tag] { ... } Name;
        (
            r"typedef\s+struct\s+(?:\w+\s+)?\{([^}]*)\}\s*([A-Za-z][A-Za-z0-9_]*)\s*;",
            "struct",
        ),
        # 3. typedef union [tag] { ... } Name;
        (
            r"typedef\s+union\s+(?:\w+\s+)?\{([^}]*)\}\s*([A-Za-z][A-Za-z0-9_]*)\s*;",
            "union",
        ),
        # 4. 数组 typedef，如 typedef BYTE_8 DEVICE_ID[3];
        (r"typedef\s+([^;]+?)\s+([A-Za-z][A-Za-z0-9_]*)\s*\[([^\]]*)\]\s*;", "array"),
        # 5. 普通 typedef（排除包含 struct/enum/union 的，避免误匹配）
        (
            r"typedef\s+(?!struct|enum|union)([^;]+?)\s+([A-Za-z][A-Za-z0-9_]*)\s*;",
            "typedef",
        ),
    ]

    for pattern, kind in patterns:
        for match in re.finditer(pattern, header_text, re.DOTALL):
            start, end = match.start(), match.end()
            if is_in_comment(start):
                continue
            if kind == "enum":
                body, name = match.groups()
                values = [
                    v.strip() for v in body.replace("\n", " ").split(",") if v.strip()
                ]
                definition = {"kind": "enum", "name": name, "values": values}
            elif kind in ("struct", "union"):
                body, name = match.groups()
                members = [m.strip() + ";" for m in body.split(";") if m.strip()]
                if len(members) == 1:
                    member = members[0].rstrip(";")
                    if re.search(r"\[[^\]]+\]", member):
                        orig_type = member
                        definition = {
                            "kind": "typedef",
                            "name": name,
                            "original_type": orig_type,
                        }
                    else:
                        definition = {"kind": kind, "name": name, "members": members}
                else:
                    definition = {"kind": kind, "name": name, "members": members}
            elif kind == "array":
                orig, name, array_size = match.groups()
                definition = {
                    "kind": "typedef",
                    "name": name,
                    "original_type": orig.strip() + f"[{array_size}]",
                }
            else:  # typedef
                orig, name = match.groups()
                definition = {
                    "kind": "typedef",
                    "name": name,
                    "original_type": orig.strip(),
                }
            if kind in ("array", "typedef") and (
                "struct" in definition.get("original_type", "")
                or "{" in definition.get("original_type", "")
            ):
                continue

            matches.append((start, end, name, definition))

    matches.sort(key=lambda x: x[0])
    comment_spans.sort(key=lambda x: x[1])

    for start, end, name, definition in matches:
        best_comment = None
        best_end = -1
        for c_start, c_end, c_text in comment_spans:
            if c_end <= start and c_end > best_end:
                best_end = c_end
                best_comment = c_text
        if best_comment:
            if best_comment.startswith("/*") and best_comment.endswith("*/"):
                cleaned = best_comment[2:-2].strip()
            elif best_comment.startswith("//"):
                cleaned = best_comment[2:].strip()
            else:
                cleaned = best_comment.strip()
            lines = cleaned.split("\n")
            cleaned_lines = []
            for line in lines:
                line = line.lstrip("*").strip()
                cleaned_lines.append(line)
            cleaned = "\n".join(cleaned_lines)
            definition["comment"] = cleaned
        else:
            definition["comment"] = None

        definition["source_file"] = source_file
        type_defs[name] = definition

    return type_defs
