"""
Extract Ada type definitions from .ads files using tree-sitter.

Handles records, enumerations, access types, array types, derived types, and subtypes.
"""

import os
import json
import logging

import tree_sitter_ada
from tree_sitter import Language, Parser

from core.utils import get_node_text, decode_file, highlight_message, collect_source_files
from parsers.ada._utils import find_ada_identifier
from parsers.common import (
    load_previous_type_cache,
    write_types_cache,
    enrich_type_definition,
    summarize_ai_result,
    is_missing_type_description,
    refresh_type_definitions,
)

logger = logging.getLogger(__name__)

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

    def traverse(node):
        if node.type == "full_type_declaration":
            name_node = find_ada_identifier(node)
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
            name_node = find_ada_identifier(node)
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

