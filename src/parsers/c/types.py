"""
Extract type definitions (structs, unions, enums, typedefs) from all .h files in the specified folder,
exclude commented-out types, associate the preceding comments, and output a JSON file with the numbering format A_1, A_2, ...
"""

import os
import re
import json
import time
import argparse
import logging
import tempfile
import copy
from core.utils import decode_file, highlight_message, collect_source_files
from core.compare import compare_types
from core.ai import ai_prompt_for_type, call_ai_from_config, AI_FAILED

logger = logging.getLogger(__name__)
AI_RESULT_PREVIEW_CHARS = 24


def load_previous_type_cache(cache_path):
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault(
                "description",
                "Type definitions extracted from project header files (excluding commented-out ones).",
            )
            data.setdefault("type_definitions", {})
            data.setdefault("type_references", {})
            return data, cache_path
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to load previous type cache from %s", cache_path)

    return {
        "description": "Type definitions extracted from project header files (excluding commented-out ones).",
        "type_definitions": {},
        "type_references": {},
    }, None


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


def write_types_cache(cache_path, master_data):
    master_types = master_data.get("type_definitions", {})
    sorted_names = sorted(master_types.keys())
    master_data["type_references"] = {
        name: f"A_{idx+1}" for idx, name in enumerate(sorted_names)
    }

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=os.path.dirname(cache_path), delete=False
    ) as tmp_file:
        json.dump(master_data, tmp_file, indent=2, ensure_ascii=False)
        tmp_path = tmp_file.name
    os.replace(tmp_path, cache_path)


def enrich_type_definition(type_name, type_definition):
    prompt = ai_prompt_for_type(type_name, type_definition)
    description = call_ai_from_config(prompt)
    type_definition["type_description"] = description
    if description == AI_FAILED:
        logger.debug("Marked type as AI failed: %s", type_name)
    else:
        logger.debug("Generated AI description for type: %s", type_name)
    return type_definition["type_description"]


def summarize_ai_result(description):
    normalized = " ".join(str(description).split())
    success = normalized != AI_FAILED
    preview = normalized[:AI_RESULT_PREVIEW_CHARS]
    if len(normalized) > AI_RESULT_PREVIEW_CHARS:
        preview = f"{preview}..."
    return "success" if success else "failed", preview


def is_missing_type_description(type_definition):
    description = type_definition.get("type_description")
    if not isinstance(description, str) or not description.strip():
        return True
    return description == AI_FAILED


def refresh_type_definitions(fresh_types, project_dir, output_dir=".analysis", enable_ai=True):
    folder_name = os.path.basename(os.path.normpath(project_dir))
    cache_path = os.path.join(output_dir, f"{folder_name}_global_types.json")
    previous_data, loaded_from = load_previous_type_cache(cache_path)
    previous_types = previous_data.get("type_definitions", {})
    diff = compare_types(previous_types, fresh_types)

    added = diff.get("added", {})
    modified = diff.get("modified", {})
    removed = diff.get("removed", {})
    changed_names = sorted(set(added.keys()) | set(modified.keys()))
    if enable_ai:
        missing_description_names = {
            type_name
            for type_name, type_definition in fresh_types.items()
            if is_missing_type_description(previous_types.get(type_name, {}))
        }
        changed_names = sorted(set(changed_names) | missing_description_names)

    logger.debug(
        "Type changes: added=%s modified=%s removed=%s",
        len(added),
        len(modified),
        len(removed),
    )

    master_data = {
        "description": "Type definitions extracted from project header files (excluding commented-out ones).",
        "type_definitions": copy.deepcopy(previous_types),
    }
    master_types = master_data["type_definitions"]

    for type_name in removed.keys():
        if type_name in master_types:
            del master_types[type_name]
            logger.debug("Removed type: %s", type_name)

    for type_name in changed_names:
        fresh_definition = copy.deepcopy(
            modified.get(type_name) or added.get(type_name) or fresh_types[type_name]
        )
        if not enable_ai:
            fresh_definition["type_description"] = ""
            logger.debug("Left description empty for type without AI: %s", type_name)
        master_types[type_name] = fresh_definition

    should_persist_now = bool(
        changed_names
        or removed
        or loaded_from != cache_path
        or not os.path.exists(cache_path)
    )

    if enable_ai:
        if changed_names:
            logger.info(
                highlight_message(
                    "Refreshing AI descriptions for %s changed types"
                ),
                len(changed_names),
            )
        else:
            logger.info(highlight_message("No types require AI refresh"))
        for index, type_name in enumerate(changed_names, start=1):
            description = enrich_type_definition(type_name, master_types[type_name])
            status, preview = summarize_ai_result(description)
            logger.info(
                "AI progress %s/%s: %s [%s] %s",
                index,
                len(changed_names),
                type_name,
                status,
                preview,
            )
            write_types_cache(cache_path, master_data)
            time.sleep(0.15)
    elif should_persist_now:
        write_types_cache(cache_path, master_data)

    if enable_ai and not changed_names and should_persist_now:
        write_types_cache(cache_path, master_data)

    logger.debug("Added: %s types", len(added))
    logger.debug("Modified: %s types", len(modified))
    logger.debug("Removed: %s types", len(removed))

    logger.debug("Type definitions saved to %s", cache_path)
    logger.debug("Total types found: %s", len(master_types))
    return master_data


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
