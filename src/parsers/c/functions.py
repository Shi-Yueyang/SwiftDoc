"""
Module Analysis Tool for C files.

Extract function definitions from  .c file, analyze parameters 、 global variables and function,
and output a JSON file with function signatures, input kinds, directions, types, and type references.

Example:
    python analyze_module.py ATP_CODE/bsw_manager.c --types .analysis/ATP_CODE_global_types.json --globals .analysis/global_variables.json --output .analysis
"""

import os
import re
import json
import time
import argparse
import logging
import tempfile
import copy
import chardet
import tree_sitter_c
from tree_sitter import Language, Parser
from core.utils import get_node_text, find_identifier, highlight_message, collect_source_files
from core.ai import ai_prompt_for_function, call_ai_from_config, AI_FAILED
from core.compare import compare_functions

logger = logging.getLogger(__name__)
AI_RESULT_PREVIEW_CHARS = 24

C_LANGUAGE = Language(tree_sitter_c.language())
parser = Parser(C_LANGUAGE)


# 提取形参
def find_parameters(declarator_node):
    params = []
    param_node = declarator_node.child_by_field_name("parameter_list")
    if param_node is None:
        for child in declarator_node.children:
            if child.type == "parameter_list":
                param_node = child
                break
    if param_node is None:
        return params
    for param in param_node.children:
        if not param.is_named:
            continue
        if param.type == "parameter_declaration":
            param_name_node = find_identifier(param)
            if param_name_node is None:
                continue
            param_name = get_node_text(param_name_node)
            type_node = param.child_by_field_name("type")
            if type_node is not None:
                param_type = get_node_text(type_node).strip()
            else:
                full_text = get_node_text(param)
                param_type = full_text.replace(param_name, "").strip()
                param_type = param_type.rstrip(",").strip()
            params.append({"name": param_name, "type": param_type})
    return params


# 提取return语句
def find_return_statements(func_body_node):
    returns = []
    if func_body_node is None:
        return returns
    stack = [func_body_node]
    while stack:
        node = stack.pop()
        if node.type == "return_statement":
            text = get_node_text(node)
            expr = text.replace("return", "").strip()
            if expr.endswith(";"):
                expr = expr[:-1].strip()
            returns.append(expr)
        else:
            for child in node.children:
                stack.append(child)
    return returns


# 提取全局变量对应类型
def get_type_ref(type_str, type_refs):
    import re

    matches = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", type_str)
    for base in reversed(matches):
        if base in type_refs:
            return type_refs[base]
    if type_str in type_refs:
        return type_refs[type_str]
    return None


# 分辨全局变量数据方向
def is_identifier_written(node):
    parent = node.parent
    if parent is None:
        return False
    if parent.type == "assignment_expression":
        left = parent.child_by_field_name("left")
        if left and find_identifier(left) == node:
            return True
    if parent.type == "update_expression":
        operand = parent.child_by_field_name("argument")
        if operand and find_identifier(operand) == node:
            return True
    return False


# 提取函数调用关系
def extract_calls_from_body(body_node):
    called = set()
    if body_node is None:
        return []
    stack = [body_node]
    while stack:
        node = stack.pop()
        if node.type == "call_expression":
            func_node = node.child_by_field_name("function")
            if func_node:
                ident = find_identifier(func_node)
                if ident:
                    called.add(get_node_text(ident))
        for child in node.children:
            stack.append(child)
    return list(called)


# 提取函数
# body_code部分（用于ai分析）
def clean_function_body(body_code):
    """
    清理函数体，去掉注释、\t 和 \n。
    """
    # 去掉单行注释
    body_code = re.sub(r"//.*", "", body_code)
    # 去掉多行注释
    body_code = re.sub(r"/\*.*?\*/", "", body_code, flags=re.DOTALL)
    # 去掉多余的空白字符和换行符
    body_code = body_code.replace("\t", "").replace("\n", "").strip()
    return body_code


# normalized_body部分（用于对比代码改动）
def normalize_c_code(code: str) -> str:
    """
    规范化C代码：去除注释和所有空白字符（空格、制表符、换行等），
    但保护字符串和字符常量不变。用于机器对比。
    """
    if not code:
        return ""
    # 保护字符串和字符常量
    placeholders = []

    def repl(match):
        placeholders.append(match.group(0))
        return f"\x00STR{len(placeholders)-1}\x00"

    # 匹配双引号字符串（支持转义）
    code = re.sub(r'"(?:\\.|[^"\\])*"', repl, code)
    # 匹配单引号字符常量
    code = re.sub(r"'(?:\\.|[^'\\])*'", repl, code)
    # 去除多行注释 /* ... */
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    # 去除单行注释 // ...
    code = re.sub(r"//.*", "", code)
    # 去除所有空白字符
    code = re.sub(r"\s+", "", code)
    # 恢复字符串和字符常量
    for i, s in enumerate(placeholders):
        code = code.replace(f"\x00STR{i}\x00", s)
    return code


def build_global_lookup(globals_list):
    external_globals = {}
    static_globals = {}
    for global_info in globals_list:
        name = global_info.get("name")
        file_path = global_info.get("file")
        if not name:
            continue
        if global_info.get("is_static") and file_path:
            static_globals[(file_path, name)] = global_info
        else:
            external_globals.setdefault(name, global_info)
    return {"external": external_globals, "static": static_globals}


def resolve_global_info(global_lookup, c_file_path, name):
    static_info = global_lookup["static"].get((c_file_path, name))
    if static_info is not None:
        return static_info
    return global_lookup["external"].get(name)


def extract_functions_from_c_file(c_file_path, type_refs, global_lookup):
    """
    Parse a single .c file and return a list of information for all functions in the file.
    Each element is a dictionary containing:
        name, file, inputs, returns, body_code, calls
    """
    with open(c_file_path, "rb") as f:
        raw = f.read()
    detected = chardet.detect(raw)
    encoding = detected.get("encoding", "utf-8")
    code = raw.decode(encoding, errors="ignore")
    tree = parser.parse(bytes(code, "utf8"))
    root_node = tree.root_node

    functions = []
    for child in root_node.children:
        if child.type == "function_definition":
            declarator_node = child.child_by_field_name("declarator")
            if declarator_node is None:
                continue
            func_name_node = find_identifier(declarator_node)
            if func_name_node is None:
                continue
            function_name = get_node_text(func_name_node)

            body_node = child.child_by_field_name("body")
            body_code = ""
            if body_node:
                full_body_text = get_node_text(body_node)
                if full_body_text.startswith("{") and full_body_text.endswith("}"):
                    body_code = full_body_text[1:-1].strip()
                else:
                    body_code = full_body_text.strip()
                body_code = clean_function_body(body_code)

            normalized_body = normalize_c_code(body_code) if body_code else ""

            params = find_parameters(declarator_node)
            inputs = []
            for p in params:
                inputs.append(
                    {
                        "name": p["name"],
                        "kind": "parameter",
                        "direction": "in",
                        "type": p["type"],
                        "type_ref": "",
                    }
                )

            if body_node:
                global_written = set()
                global_read = set()
                referenced_globals = {}
                stack = [body_node]
                while stack:
                    node = stack.pop()
                    if node.type == "identifier":
                        name = get_node_text(node)
                        global_info = resolve_global_info(global_lookup, c_file_path, name)
                        if global_info is not None:
                            referenced_globals[name] = global_info
                            if is_identifier_written(node):
                                global_written.add(name)
                            else:
                                global_read.add(name)
                    else:
                        for sub in node.children:
                            stack.append(sub)

                for gname in global_read | global_written:
                    ginfo = referenced_globals[gname]
                    gtype = ginfo["type"]
                    direction = "in out" if gname in global_written else "in"
                    type_ref = get_type_ref(gtype, type_refs)
                    if type_ref is None:
                        type_ref = ""
                    inputs.append(
                        {
                            "name": gname,
                            "kind": "Global variable",
                            "direction": direction,
                            "type": gtype,
                            "type_ref": type_ref,
                        }
                    )

            return_exprs = find_return_statements(body_node)
            calls = extract_calls_from_body(body_node)

            functions.append(
                {
                    "name": function_name,
                    "file": c_file_path,
                    "inputs": inputs,
                    "returns": return_exprs,
                    "body_code": body_code,
                    "normalized_body": normalized_body,
                    "calls": calls,
                }
            )
    return functions


def load_previous_function_cache(output_json_path):
    if os.path.exists(output_json_path):
        try:
            with open(output_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("functions", [])
            return data, output_json_path
        except (json.JSONDecodeError, OSError):
            logger.warning(
                "Failed to load previous function cache from %s", output_json_path
            )

    return {"functions": []}, None


def write_function_cache(output_json_path, output_data):
    os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=os.path.dirname(output_json_path), delete=False
    ) as tmp_file:
        json.dump(output_data, tmp_file, indent=2, ensure_ascii=False)
        tmp_path = tmp_file.name
    os.replace(tmp_path, output_json_path)


def prepare_function_metadata(func, type_descriptions=None):
    func["algorithm_logic"] = func.get("algorithm_logic", "")

    if (
        isinstance(func.get("returns"), list)
        and func["returns"]
        and isinstance(func["returns"][0], str)
    ):
        func["returns"] = [
            {"expression": expr, "return_description": ""} for expr in func["returns"]
        ]
    else:
        for ret in func.get("returns", []):
            ret["return_description"] = ret.get("return_description", "")

    for inp in func.get("inputs", []):
        inp["inputs_description"] = inp.get("inputs_description", "")
        if inp.get("kind") == "Global variable":
            base_type_match = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", inp["type"])
            base_type = base_type_match.group(1) if base_type_match else inp["type"]
            inp["type_description"] = (type_descriptions or {}).get(base_type, "")


def enrich_function_with_ai(func, type_descriptions):
    prepare_function_metadata(func, type_descriptions)

    prompt = ai_prompt_for_function(func)
    response = call_ai_from_config(prompt)
    logger.debug("AI raw response for %s:\n%s\n", func["name"], response)
    if response != AI_FAILED:
        try:
            desc = json.loads(response)
            func["algorithm_logic"] = desc.get("algorithm_logic", "")
            param_descs = {
                item["name"]: item.get("inputs_description", "")
                for item in desc.get("inputs_description", [])
            }
            for inp in func.get("inputs", []):
                inp["inputs_description"] = param_descs.get(
                    inp["name"], inp.get("inputs_description", "")
                )
            return_descs = desc.get("return_values", [])
            for idx, ret_item in enumerate(func.get("returns", [])):
                ret_item["return_description"] = (
                    return_descs[idx] if idx < len(return_descs) else ""
                )
            logger.debug("Generated AI description for function: %s", func["name"])
        except json.JSONDecodeError as exc:
            logger.debug("JSON parse failed: %s | raw response: %s", exc, response)
            func["algorithm_logic"] = AI_FAILED
            logger.debug("Marked function as AI failed: %s", func["name"])
    else:
        func["algorithm_logic"] = AI_FAILED
        logger.debug("Marked function as AI failed: %s", func["name"])
    return func["algorithm_logic"]


def summarize_ai_result(description):
    normalized = " ".join(str(description).split())
    success = normalized != AI_FAILED
    preview = normalized[:AI_RESULT_PREVIEW_CHARS]
    if len(normalized) > AI_RESULT_PREVIEW_CHARS:
        preview = f"{preview}..."
    return "success" if success else "failed", preview


def is_missing_algorithm_logic(func):
    logic = func.get("algorithm_logic")
    if not isinstance(logic, str) or not logic.strip():
        return True
    return logic == AI_FAILED


# 分析c文件
def scan_all_functions(project_dir, types_data, global_vars):
    """Scan .c files and return a list of function dicts (no cache I/O)."""
    c_files = collect_source_files(project_dir, (".c",))
    if not c_files:
        logger.debug("No .c files found in %s", project_dir)
        return []

    type_refs = types_data.get("type_references", {})
    global_lookup = build_global_lookup(global_vars)
    all_functions = []
    for cf in c_files:
        funcs = extract_functions_from_c_file(cf, type_refs, global_lookup)
        all_functions.extend(funcs)

    # Resolve called_by
    known_names = {func["name"] for func in all_functions}
    called_by_map = {}
    for func in all_functions:
        for callee in func.get("calls", []):
            if callee in known_names:
                called_by_map.setdefault(callee, []).append(func["name"])
    for callee, callers in called_by_map.items():
        called_by_map[callee] = list(set(callers))
    for func in all_functions:
        func["called_by"] = called_by_map.get(func["name"], [])

    return all_functions


def refresh_functions(
    all_functions,
    output_json_path,
    types_data,
    enable_ai=True,
):
    type_descriptions = {
        name: info["type_description"]
        for name, info in types_data.get("type_definitions", {}).items()
        if isinstance(info, dict) and "type_description" in info
    }
    previous_data, loaded_from = load_previous_function_cache(output_json_path)
    previous_functions = previous_data.get("functions", [])
    def _func_key(f):
        return (f["name"], f["file"])

    diff = compare_functions(previous_functions, all_functions)

    added = diff.get("added", [])
    modified = diff.get("modified", [])
    removed = diff.get("removed", [])
    changed_functions = [*added, *(item["new"] for item in modified)]
    if enable_ai:
        missing_logic_keys = {
            _func_key(func)
            for func in previous_functions
            if is_missing_algorithm_logic(func)
        }
        changed_function_map = {_func_key(func): func for func in changed_functions}
        for func in all_functions:
            if _func_key(func) in missing_logic_keys:
                changed_function_map[_func_key(func)] = func
        changed_functions = list(changed_function_map.values())

    output_data = {"functions": copy.deepcopy(previous_functions)}
    function_map = {_func_key(func): func for func in output_data["functions"]}

    for func in removed:
        key = _func_key(func)
        if key in function_map:
            del function_map[key]
            logger.debug("Removed function: %s (%s)", func["name"], func.get("file"))

    for func in changed_functions:
        fresh_function = copy.deepcopy(func)
        if not enable_ai:
            fresh_function["algorithm_logic"] = ""
        prepare_function_metadata(fresh_function, type_descriptions)
        function_map[_func_key(fresh_function)] = fresh_function

    should_persist_now = bool(
        changed_functions
        or removed
        or loaded_from != output_json_path
        or not os.path.exists(output_json_path)
    )

    if enable_ai:
        if changed_functions:
            logger.info(
                highlight_message(
                    "Refreshing AI descriptions for %s changed functions"
                ),
                len(changed_functions),
            )
        else:
            logger.info(highlight_message("No functions require AI refresh"))
        for index, func in enumerate(changed_functions, start=1):
            current_function = function_map[_func_key(func)]
            description = enrich_function_with_ai(current_function, type_descriptions)
            status, preview = summarize_ai_result(description)
            logger.info(
                "AI progress %s/%s: %s [%s] %s",
                index,
                len(changed_functions),
                current_function["name"],
                status,
                preview,
            )
            output_data["functions"] = list(function_map.values())
            write_function_cache(output_json_path, output_data)

            time.sleep(0.5)
    elif should_persist_now:
        output_data["functions"] = list(function_map.values())
        write_function_cache(output_json_path, output_data)

    if enable_ai and not changed_functions and should_persist_now:
        output_data["functions"] = list(function_map.values())
        write_function_cache(output_json_path, output_data)

    logger.debug("Added: %s functions", len(added))
    logger.debug("Modified: %s functions", len(modified))
    logger.debug("Removed: %s functions", len(removed))
    logger.debug("Total functions: %s", len(function_map))
    logger.debug("All functions saved to %s", output_json_path)

    return output_json_path


