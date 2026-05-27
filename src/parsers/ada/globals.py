"""
Extract package-level variable declarations from Ada .ads and .adb files using tree-sitter.
"""

import logging

import tree_sitter_ada
from tree_sitter import Language, Parser

from core.utils import get_node_text, decode_file, collect_source_files
from parsers.ada._utils import find_ada_identifier

logger = logging.getLogger(__name__)

ADA_LANGUAGE = Language(tree_sitter_ada.language())
ada_parser = Parser(ADA_LANGUAGE)


def _is_inside_subprogram(node):
    """Check if a node is inside a subprogram_body or subprogram_declaration."""
    current = node.parent
    while current:
        if current.type in ("subprogram_body", "subprogram_declaration"):
            return True
        current = current.parent
    return False


def collect_globals_from_ada_file(file_path):
    """Extract package-level variable declarations from a single Ada file."""
    with open(file_path, "rb") as f:
        raw = f.read()
    text = decode_file(raw)
    tree = ada_parser.parse(bytes(text, "utf8"))
    root_node = tree.root_node

    globals_list = []

    def traverse(node):
        if node.type == "object_declaration" and not _is_inside_subprogram(node):
            name_node = find_ada_identifier(node)
            if name_node is None:
                return
            var_name = get_node_text(name_node)

            # Determine type: find the second identifier (after ':')
            identifiers = [c for c in node.children if c.is_named and c.type == "identifier"]
            if len(identifiers) >= 2:
                var_type = get_node_text(identifiers[1])
            else:
                # Fallback: get text between ':' and ':=' or ';'
                full = get_node_text(node)
                var_type = "unknown"
                if ":" in full:
                    after_colon = full.split(":", 1)[1].strip()
                    for sep in (";", ":="):
                        if sep in after_colon:
                            after_colon = after_colon.split(sep, 1)[0]
                    var_type = after_colon.strip()

            # Check for constant
            is_constant = any(
                c.type == "constant" or (not c.is_named and get_node_text(c) == "constant")
                for c in node.children
            )

            globals_list.append({
                "name": var_name,
                "type": var_type,
                "file": file_path,
                "kind": "definition",
                "is_static": False,
            })

        for child in node.children:
            traverse(child)

    traverse(root_node)
    return globals_list


def extract_all_globals(project_dir):
    """Extract all package-level variables from .ads and .adb files."""
    ads_files = collect_source_files(project_dir, (".ads",))
    adb_files = collect_source_files(project_dir, (".adb",))
    all_files = ads_files + adb_files

    all_globals = {}
    for f in all_files:
        for v in collect_globals_from_ada_file(f):
            key = v["name"]
            if key not in all_globals:
                all_globals[key] = v

    return list(all_globals.values())
