
"""
Extract all global variables (including static) from .c and .h files in a given directory.
Outputs a JSON file with variable name, type, file, kind (definition/extern), and is_static flag.
"""

import logging
import chardet
import tree_sitter_c
from tree_sitter import Language, Parser
from core.utils import get_node_text, find_identifier, collect_source_files, filter_source_files_by_analyse_dirs


logger = logging.getLogger(__name__)

C_LANGUAGE = Language(tree_sitter_c.language())
parser = Parser(C_LANGUAGE)


def is_inside_function(node):
    while node.parent:
        if node.parent.type == 'function_definition':
            return True
        node = node.parent
    return False


def collect_globals_from_c_file(c_file_path):
    with open(c_file_path, 'rb') as f:
        raw_data = f.read()
    detected = chardet.detect(raw_data)
    encoding = detected['encoding'] or 'utf-8'
    code = raw_data.decode(encoding, errors='ignore')
    tree = parser.parse(bytes(code, 'utf8'))
    root_node = tree.root_node

    global_vars = []

    def traverse(node):
        if node.type == 'declaration' and not is_inside_function(node):
            declarator = node.child_by_field_name('declarator')
            if declarator and declarator.type == 'function_declarator':
                return
            storage_specs = [
                get_node_text(child)
                for child in node.children
                if child.type == 'storage_class_specifier'
            ]
            has_static = 'static' in storage_specs
            has_extern = 'extern' in storage_specs
            if has_extern:
                return  # extern in .c is just a declaration, skip
            var_name_node = find_identifier(node)
            if var_name_node is None:
                return
            var_name = get_node_text(var_name_node)
            type_node = node.child_by_field_name('type')
            if type_node is None:
                return
            var_type = get_node_text(type_node).strip()
            global_vars.append({
                "name": var_name,
                "type": var_type,
                "definition": None,
                "file": c_file_path,
                "kind": "definition",
                "is_static": has_static
            })
        for child in node.children:
            traverse(child)

    traverse(root_node)
    return global_vars


def collect_extern_from_h_file(h_file_path):
    with open(h_file_path, 'rb') as f:
        raw_data = f.read()
    detected = chardet.detect(raw_data)
    encoding = detected['encoding'] or 'utf-8'
    code = raw_data.decode(encoding, errors='ignore')
    tree = parser.parse(bytes(code, 'utf8'))
    root_node = tree.root_node

    extern_vars = []

    def traverse(node):
        if node.type == 'declaration':
            has_extern = any(
                child.type == 'storage_class_specifier' and get_node_text(child) == 'extern'
                for child in node.children
            )
            if not has_extern:
                return
            declarator = node.child_by_field_name('declarator')
            is_func = False
            if declarator:
                if declarator.type == 'function_declarator':
                    is_func = True
                else:
                    stack = [declarator]
                    while stack:
                        n = stack.pop()
                        if n.type == 'parameter_list':
                            is_func = True
                            break
                        stack.extend(n.children)
            if is_func:
                return
            var_name_node = find_identifier(node)
            if var_name_node is None:
                return
            var_name = get_node_text(var_name_node)
            type_node = node.child_by_field_name('type')
            if type_node is None:
                return
            var_type = get_node_text(type_node).strip()
            extern_vars.append({
                "name": var_name,
                "type": var_type,
                "definition": None,
                "file": h_file_path,
                "kind": "extern",
                "is_static": False
            })
        for child in node.children:
            traverse(child)

    traverse(root_node)
    return extern_vars


def get_global_key(global_info):
    if global_info.get("is_static"):
        return global_info["name"], global_info["file"]
    return global_info["name"]


def extract_all_globals(project_dir, analyse_dirs=None):
    c_files = collect_source_files(project_dir, (".c",))
    if analyse_dirs is not None:
        c_files = filter_source_files_by_analyse_dirs(c_files, analyse_dirs)
    h_files = collect_source_files(project_dir, (".h",))
    all_globals = {}

    for cf in c_files:
        vars_list = collect_globals_from_c_file(cf)
        for v in vars_list:
            global_key = get_global_key(v)
            existing = all_globals.get(global_key)
            if existing is None:
                all_globals[global_key] = v
            elif existing.get("kind") == "extern" and v.get("kind") == "definition":
                all_globals[global_key] = v
            else:
                logger.warning(
                    "Duplicate definition of '%s' in %s, previous in %s",
                    v["name"], cf, existing["file"],
                )

    for hf in h_files:
        vars_list = collect_extern_from_h_file(hf)
        for v in vars_list:
            global_key = get_global_key(v)
            if global_key not in all_globals:
                all_globals[global_key] = v
            # If a definition already exists, don't overwrite with extern

    return list(all_globals.values())