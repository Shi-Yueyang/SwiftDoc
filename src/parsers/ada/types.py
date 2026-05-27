"""
Extract Ada type definitions from .ads files using tree-sitter.

Handles records, enumerations, access types, array types, derived types, and subtypes.
"""

import os
import json
import time
import logging
import tempfile
import copy

import tree_sitter_ada
from tree_sitter import Language, Parser

from core.utils import get_node_text, decode_file, highlight_message, collect_source_files
from core.compare import compare_types
from core.ai import ai_prompt_for_type, call_ai_from_config, AI_FAILED

logger = logging.getLogger(__name__)
AI_RESULT_PREVIEW_CHARS = 24

ADA_LANGUAGE = Language(tree_sitter_ada.language())
ada_parser = Parser(ADA_LANGUAGE)


def _get_comment_before(node, source_lines):
    """Find the nearest -- comment before a node's start line."""
    start_row = node.start_point[0]
    if start_row == 0:
        return None
    prev_line = source_lines[start_row - 1].strip()
    if prev_line.startswith("--"):
        return prev_line[2:].strip()
    return None


def _extract_component_list(component_list_node):
    """Extract member declarations from a component_list node."""
    members = []
    for child in component_list_node.children:
        if child.type == "component_declaration":
            member_text = get_node_text(child).strip()
            if member_text.endswith(";"):
                member_text = member_text[:-1].strip()
            members.append(member_text)
    return members


def collect_ada_types_from_file(file_path):
    """Extract all type definitions from a single .ads file."""
    with open(file_path, "rb") as f:
        raw = f.read()
    text = decode_file(raw)
    source_lines = text.split("\n")
    tree = ada_parser.parse(bytes(text, "utf8"))
    root_node = tree.root_node

    type_defs = {}

    def _find_identifier(node):
        """Find the first named identifier child."""
        for child in node.children:
            if child.is_named and child.type == "identifier":
                return child
        return None

    def traverse(node):
        if node.type == "full_type_declaration":
            name_node = _find_identifier(node)
            if name_node is None:
                return
            name = get_node_text(name_node)

            definition = {"source_file": file_path}

            # Find the type definition child (after 'type', 'is')
            def_children = [c for c in node.children if c.is_named and c != name_node]

            if not def_children:
                return

            # The first named child after the name is the type definition
            def_child = def_children[0]

            if def_child.type == "record_type_definition":
                # Walk into record_definition -> component_list
                for sub in def_child.children:
                    if sub.type == "record_definition":
                        for sub2 in sub.children:
                            if sub2.type == "component_list":
                                members = _extract_component_list(sub2)
                                definition["kind"] = "struct"
                                definition["name"] = name
                                definition["members"] = members
                                break
                        break

            elif def_child.type == "enumeration_type_definition":
                values = []
                for sub in def_child.children:
                    if sub.is_named and sub.type == "identifier":
                        values.append(get_node_text(sub))
                definition["kind"] = "enum"
                definition["name"] = name
                definition["values"] = values

            elif def_child.type == "access_to_object_definition":
                original = get_node_text(def_child).strip()
                definition["kind"] = "typedef"
                definition["name"] = name
                definition["original_type"] = original

            elif def_child.type == "array_type_definition":
                original = get_node_text(def_child).strip()
                definition["kind"] = "typedef"
                definition["name"] = name
                definition["original_type"] = original

            else:
                # Derived type or other: type Name is new Base;
                # Collect text from 'is' keyword onward
                is_found = False
                parts = []
                for child in node.children:
                    if not is_found:
                        text_seg = get_node_text(child)
                        if text_seg == "is":
                            is_found = True
                        continue
                    if child.is_named:
                        parts.append(get_node_text(child))
                original = " ".join(parts).rstrip(";").strip()
                if original:
                    definition["kind"] = "typedef"
                    definition["name"] = name
                    definition["original_type"] = original
                else:
                    return

            # Associate preceding comment
            comment = _get_comment_before(node, source_lines)
            definition["comment"] = comment

            type_defs[name] = definition

        elif node.type == "subtype_declaration":
            name_node = _find_identifier(node)
            if name_node is None:
                return
            name = get_node_text(name_node)

            # Collect everything after 'is'
            is_found = False
            parts = []
            for child in node.children:
                if not is_found:
                    text_seg = get_node_text(child)
                    if text_seg == "is":
                        is_found = True
                    continue
                if child.is_named:
                    parts.append(get_node_text(child))
            original = " ".join(parts).rstrip(";").strip()

            if original:
                definition = {
                    "kind": "typedef",
                    "name": name,
                    "original_type": original,
                    "source_file": file_path,
                }
                comment = _get_comment_before(node, source_lines)
                definition["comment"] = comment
                type_defs[name] = definition

        for child in node.children:
            traverse(child)

    traverse(root_node)
    return type_defs


def scan_project_types(project_dir):
    """Scan .ads files and return a dict of type definitions."""
    ads_files = collect_source_files(project_dir, (".ads",))
    all_types = {}
    for f in ads_files:
        file_types = collect_ada_types_from_file(f)
        for name, defn in file_types.items():
            if name not in all_types:
                all_types[name] = defn
            else:
                existing = all_types[name]
                if existing.get("kind") == "typedef" and defn.get("kind") != "typedef":
                    all_types[name] = defn
    return all_types


# --- Cache / refresh / AI (reused pattern from C parser) ---

def load_previous_type_cache(cache_path):
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("description", "")
            data.setdefault("type_definitions", {})
            data.setdefault("type_references", {})
            return data, cache_path
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to load previous type cache from %s", cache_path)

    return {"description": "", "type_definitions": {}, "type_references": {}}, None


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
        missing_desc_names = {
            name
            for name, defn in fresh_types.items()
            if is_missing_type_description(previous_types.get(name, {}))
        }
        changed_names = sorted(set(changed_names) | missing_desc_names)

    master_data = {"description": "", "type_definitions": copy.deepcopy(previous_types)}
    master_types = master_data["type_definitions"]

    for type_name in removed.keys():
        if type_name in master_types:
            del master_types[type_name]

    for type_name in changed_names:
        fresh_definition = copy.deepcopy(
            modified.get(type_name) or added.get(type_name) or fresh_types[type_name]
        )
        if not enable_ai:
            fresh_definition["type_description"] = ""
        master_types[type_name] = fresh_definition

    should_persist = bool(
        changed_names or removed or loaded_from != cache_path or not os.path.exists(cache_path)
    )

    if enable_ai:
        if changed_names:
            logger.info(highlight_message("Refreshing AI descriptions for %s changed types"), len(changed_names))
        else:
            logger.info(highlight_message("No types require AI refresh"))
        for idx, type_name in enumerate(changed_names, start=1):
            description = enrich_type_definition(type_name, master_types[type_name])
            status, preview = summarize_ai_result(description)
            logger.info("AI progress %s/%s: %s [%s] %s", idx, len(changed_names), type_name, status, preview)
            write_types_cache(cache_path, master_data)
            time.sleep(0.15)
    elif should_persist:
        write_types_cache(cache_path, master_data)

    if enable_ai and not changed_names and should_persist:
        write_types_cache(cache_path, master_data)

    return master_data
