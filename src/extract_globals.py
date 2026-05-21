
"""
Extract all global variables (including static) from .c and .h files in a given directory.
Outputs a JSON file with variable name, type, file, kind (definition/extern), and is_static flag.
"""

import os
import json
import logging
import chardet
import tree_sitter_c
from tree_sitter import Language, Parser
from utils import get_node_text, find_identifier


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
            has_static = any(
                child.type == 'storage_class_specifier' and get_node_text(child) == 'static'
                for child in node.children
            )
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


def extract_all_globals(project_dir):
    c_files = []
    h_files = []
    
    # If project_dir is a file, only process that file
    if os.path.isfile(project_dir):
        if project_dir.endswith('.c'):
            c_files.append(project_dir)
        elif project_dir.endswith('.h'):
            h_files.append(project_dir)
    else:
        # Otherwise walk the directory
        for root, _, files in os.walk(project_dir):
            for f in files:
                full = os.path.join(root, f)
                if f.endswith('.c'):
                    c_files.append(full)
                elif f.endswith('.h'):
                    h_files.append(full)

    logger.info("Found %s .c files, %s .h files", len(c_files), len(h_files))
    all_globals = {}

    for cf in c_files:
        vars_list = collect_globals_from_c_file(cf)
        for v in vars_list:
            global_key = get_global_key(v)
            if global_key not in all_globals:
                all_globals[global_key] = v
            else:
                logger.warning(
                    "Duplicate definition of '%s' in %s, previous in %s",
                    v["name"],
                    cf,
                    all_globals[global_key]["file"],
                )

    for hf in h_files:
        vars_list = collect_extern_from_h_file(hf)
        for v in vars_list:
            global_key = get_global_key(v)
            if global_key not in all_globals:
                all_globals[global_key] = v

    return list(all_globals.values())


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Extract global variables from C/C++ project.")
    parser.add_argument("project_dir", nargs='?', default="ATP_CODE", help="Root directory of the project (contains .c and .h files)")
    parser.add_argument("--output", "-o", default=".analysis", help="Output directory (default: .analysis)")
    parser.add_argument("--outfile", "-f", default="global_variables.json", help="Output JSON filename (default: global_variables.json)")
    args = parser.parse_args()

    globals_list = extract_all_globals(args.project_dir)
    os.makedirs(args.output, exist_ok=True)
    output_file = os.path.join(args.output, args.outfile)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({"globals": globals_list}, f, indent=2, ensure_ascii=False)
    logger.info("Saved %s global variables to %s", len(globals_list), output_file)


if __name__ == "__main__":
    main()