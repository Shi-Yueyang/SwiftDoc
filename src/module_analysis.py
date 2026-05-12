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
import chardet
import tree_sitter_c
from tree_sitter import Language, Parser
from utils import get_node_text, find_identifier
from ai_utils import ai_prompt_for_function, call_ai
from version_diff import generate_versioned_filename, compare_functions, load_previous_functions

C_LANGUAGE = Language(tree_sitter_c.language())
parser = Parser(C_LANGUAGE)

#提取形参
def find_parameters(declarator_node):
    params = []
    param_node = declarator_node.child_by_field_name('parameter_list')
    if param_node is None:
        for child in declarator_node.children:
            if child.type == 'parameter_list':
                param_node = child
                break
    if param_node is None:
        return params
    for param in param_node.children:
        if not param.is_named:
            continue
        if param.type == 'parameter_declaration':
            param_name_node = find_identifier(param)
            if param_name_node is None:
                continue
            param_name = get_node_text(param_name_node)
            full_text = get_node_text(param)
            param_type = full_text.replace(param_name, '').strip()
            param_type = param_type.rstrip(',').strip()
            params.append({"name": param_name, "type": param_type})
    return params


#提取return语句
def find_return_statements(func_body_node):
    returns = []
    if func_body_node is None:
        return returns
    stack = [func_body_node]
    while stack:
        node = stack.pop()
        if node.type == 'return_statement':
            text = get_node_text(node)
            expr = text.replace('return', '').strip()
            if expr.endswith(';'):
                expr = expr[:-1].strip()
            returns.append(expr)
        else:
            for child in node.children:
                stack.append(child)
    return returns


#提取全局变量对应类型
def get_type_ref(type_str, type_refs):
    import re
    match = re.search(r'\b([A-Za-z_][A-Za-z0-9_]*)\b', type_str)
    if match:
        base = match.group(1)
        if base in type_refs:
            return type_refs[base]
    if type_str in type_refs:
        return type_refs[type_str]
    return None


#分辨全局变量数据方向
def is_identifier_written(node):
    parent = node.parent
    if parent is None:
        return False
    if parent.type == 'assignment_expression':
        left = parent.child_by_field_name('left')
        if left and find_identifier(left) == node:
            return True
    if parent.type == 'update_expression':
        operand = parent.child_by_field_name('argument')
        if operand and find_identifier(operand) == node:
            return True
    return False


#提取函数调用关系
def extract_calls_from_body(body_node):
    called = set()
    if body_node is None:
        return []
    stack = [body_node]
    while stack:
        node = stack.pop()
        if node.type == 'call_expression':
            func_node = node.child_by_field_name('function')
            if func_node:
                ident = find_identifier(func_node)
                if ident:
                    called.add(get_node_text(ident))
        for child in node.children:
            stack.append(child)
    return list(called)


#提取函数
#body_code部分（用于ai分析）
def clean_function_body(body_code):
    """
    清理函数体，去掉注释、\t 和 \n。
    """
    # 去掉单行注释
    body_code = re.sub(r'//.*', '', body_code)
    # 去掉多行注释
    body_code = re.sub(r'/\*.*?\*/', '', body_code, flags=re.DOTALL)
    # 去掉多余的空白字符和换行符
    body_code = body_code.replace('\t', '').replace('\n', '').strip()
    return body_code
#normalized_body部分（用于对比代码改动）
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
        return f'\x00STR{len(placeholders)-1}\x00'
    # 匹配双引号字符串（支持转义）
    code = re.sub(r'"(?:\\.|[^"\\])*"', repl, code)
    # 匹配单引号字符常量
    code = re.sub(r"'(?:\\.|[^'\\])*'", repl, code)
    # 去除多行注释 /* ... */
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    # 去除单行注释 // ...
    code = re.sub(r'//.*', '', code)
    # 去除所有空白字符
    code = re.sub(r'\s+', '', code)
    # 恢复字符串和字符常量
    for i, s in enumerate(placeholders):
        code = code.replace(f'\x00STR{i}\x00', s)
    return code

def extract_functions_from_c_file(c_file_path, type_refs, all_globals):
    """
    Parse a single .c file and return a list of information for all functions in the file.
    Each element is a dictionary containing:
        name, file, inputs, returns, body_code, calls
    """
    with open(c_file_path, 'rb') as f:
        raw = f.read()
    detected = chardet.detect(raw)
    encoding = detected.get('encoding', 'utf-8')
    code = raw.decode(encoding, errors='ignore')
    tree = parser.parse(bytes(code, 'utf8'))
    root_node = tree.root_node

    functions = []
    for child in root_node.children:
        if child.type == 'function_definition':
            declarator_node = child.child_by_field_name('declarator')
            if declarator_node is None:
                continue
            func_name_node = find_identifier(declarator_node)
            if func_name_node is None:
                continue
            function_name = get_node_text(func_name_node)

            body_node = child.child_by_field_name('body')
            body_code = ""
            if body_node:
                full_body_text = get_node_text(body_node)
                if full_body_text.startswith('{') and full_body_text.endswith('}'):
                    body_code = full_body_text[1:-1].strip()
                else:
                    body_code = full_body_text.strip()
                body_code = clean_function_body(body_code)
            
            normalized_body = normalize_c_code(body_code) if body_code else ""

            params = find_parameters(declarator_node)
            inputs = []
            for p in params:
                inputs.append({
                    "name": p["name"],
                    "kind": "parameter",
                    "direction": "in",
                    "type": p["type"],
                    "type_ref": ""
                })

            if body_node:
                global_written = set()
                global_read = set()
                stack = [body_node]
                while stack:
                    node = stack.pop()
                    if node.type == 'identifier':
                        name = get_node_text(node)
                        if name in all_globals:
                            if is_identifier_written(node):
                                global_written.add(name)
                            else:
                                global_read.add(name)
                    else:
                        for sub in node.children:
                            stack.append(sub)

                for gname in (global_read | global_written):
                    ginfo = all_globals[gname]
                    gtype = ginfo["type"]
                    direction = "in out" if gname in global_written else "in"
                    type_ref = get_type_ref(gtype, type_refs)
                    if type_ref is None:
                        type_ref = ""
                    inputs.append({
                        "name": gname,
                        "kind": "Global variable",
                        "direction": direction,
                        "type": gtype,
                        "type_ref": type_ref
                    })

            return_exprs = find_return_statements(body_node)
            calls = extract_calls_from_body(body_node)

            functions.append({
                "name": function_name,
                "file": c_file_path,
                "inputs": inputs,
                "returns": return_exprs,
                "body_code": body_code,
                "normalized_body": normalized_body,
                "calls": calls
            })
    return functions


#ai分析函数
def enhance_functions_with_ai(func_list, type_descriptions=None):
    """
    对给定的函数列表进行 AI 分析增强。
    参数:
        func_list: 函数字典列表（每个字典应包含 name, inputs, returns, body_code 等字段）
        type_descriptions: 字典，类型名 -> 类型描述，若为 None 则尝试从 types_json 加载
    返回:
        修改后的函数列表（原地修改）
    """

    for func in func_list:
        if isinstance(func.get('returns'), list) and func['returns'] and isinstance(func['returns'][0], str):
            func['returns'] = [{"expression": expr, "return_description": ""} for expr in func['returns']]
        else:
            for ret in func.get('returns', []):
                if 'return_description' not in ret:
                    ret['return_description'] = ""

        for inp in func.get('inputs', []):
            if 'inputs_description' not in inp:
                inp['inputs_description'] = ""

        prompt = ai_prompt_for_function(func)
        response = call_ai(prompt, temperature=1.0, max_tokens=800, retry_count=1)
        print(f"AI raw response for {func['name']}:\n{response}\n")
        if response:
            try:
                desc = json.loads(response)
                func['algorithm_logic'] = desc.get('algorithm_logic', '')
                param_descs = {item['name']: item.get('inputs_description', '') for item in desc.get('inputs_description', [])}
                for inp in func['inputs']:
                    inp['inputs_description'] = param_descs.get(inp['name'], inp.get('inputs_description', ''))
                return_descs = desc.get('return_values', [])
                for idx, ret_item in enumerate(func['returns']):
                    if idx < len(return_descs):
                        ret_item['return_description'] = return_descs[idx]
                    else:
                        ret_item['return_description'] = ''
            except json.JSONDecodeError as e:
                print(f"JSON 解析失败: {e}")
                func['algorithm_logic'] = "AI 分析失败"
        else:
            func['algorithm_logic'] = "AI 分析失败"

        for inp in func.get('inputs', []):
            if inp['kind'] == 'Global variable':
                base_type_match = re.search(r'\b([A-Za-z_][A-Za-z0-9_]*)\b', inp['type'])
                base_type = base_type_match.group(1) if base_type_match else inp['type']
                inp['type_description'] = type_descriptions.get(base_type, "")

        time.sleep(0.5)
    return func_list


#加载类型描述
def load_type_descriptions(types_json_path):
    with open(types_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    type_descs = {}
    if "type_definitions" in data:
        for name, info in data["type_definitions"].items():
            if isinstance(info, dict) and "type_description" in info:
                type_descs[name] = info["type_description"]
    elif "types" in data:
        for t in data["types"]:
            name = t.get("name")
            desc = t.get("type_description")
            if name and desc:
                type_descs[name] = desc
    elif "type_description" in data:
        for k, v in data["type_description"].items():
            type_descs[k] = v
    
    return type_descs


#分析c文件
def analyze_project_c_files(project_dir, types_json_path, globals_json_path, output_json_path, enable_ai=True, enable_version_control=True, file_filter=None):
    """
    分析项目中的所有 .c 文件，提取函数签名、调用关系等。
    
    参数:
        project_dir: 项目根目录
        types_json_path: 类型定义 JSON 文件路径（包含 type_references）
        globals_json_path: 全局变量 JSON 文件路径
        output_json_path: 输出 JSON 文件路径
        enable_ai: 是否启用 AI 增强（若为 False，则完全保留原始提取数据）
        enable_version_control: 是否启用版本管理（自动生成版本号并对比差异），默认 True
        file_filter: 可选，指定只分析某个 .c 文件（绝对路径或相对路径）
    """
    with open(types_json_path, 'r', encoding='utf-8') as f:
        types_data = json.load(f)
        type_refs = types_data.get("type_references", {})
    
    type_descriptions = load_type_descriptions(types_json_path) if enable_ai else {}

    with open(globals_json_path, 'r', encoding='utf-8') as f:
        globals_data = json.load(f)
        all_globals = {g["name"]: g for g in globals_data.get("globals", [])}
    
    c_files = []
    for root, _, files in os.walk(project_dir):
        for f in files:
            if f.endswith('.c'):
                full_path  = os.path.join(root, f)
                if file_filter:
                    if os.path.samefile(full_path, file_filter):
                        c_files.append(full_path)
                        break  
                else:
                    c_files.append(full_path)
    
    if not c_files:
        print(f"No .c files found in {project_dir}")
        return
    
    # 提取原始函数信息（无 AI 字段）
    all_functions = []
    name_to_funcs = {}
    for cf in c_files:
        funcs = extract_functions_from_c_file(cf, type_refs, all_globals)
        for func in funcs:
            all_functions.append(func)
            name = func["name"]
            name_to_funcs.setdefault(name, []).append(func)
    
    # 构建调用关系 called_by（谁调用了当前函数）
    called_by_map = {}
    for func in all_functions:
        caller = func["name"]
        for callee in func["calls"]:
            if callee in name_to_funcs:
                called_by_map.setdefault(callee, []).append(caller)
    for callee, callers in called_by_map.items():
        called_by_map[callee] = list(set(callers))
    for func in all_functions:
        func["called_by"] = called_by_map.get(func["name"], [])
    
    # 根据 enable_ai 决定是否添加 AI 增强字段
    if enable_ai:
        all_functions = enhance_functions_with_ai(all_functions, type_descriptions)
    else:
        pass

    # 根据 enable_version_control 决定是否对比新旧代码
    if enable_version_control:
        old_functions = load_previous_functions(output_json_path)
        if old_functions:
            print(f"Found previous version: {output_json_path}")
            final_output_path = generate_versioned_filename(output_json_path)
        else:
            final_output_path = output_json_path
    else:
        old_functions = []
        final_output_path = output_json_path
    
    os.makedirs(os.path.dirname(final_output_path), exist_ok=True)
    output_data = {"functions": all_functions}
    with open(final_output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    print(f"All functions saved to {final_output_path}")
    print(f"Total functions: {len(all_functions)}")

    if enable_version_control and old_functions:
        diff = compare_functions(old_functions, all_functions)
        diff_path = os.path.join(os.path.dirname(final_output_path), "functions_diff.json")
        with open(diff_path, 'w', encoding='utf-8') as f:
            json.dump(diff, f, indent=2, ensure_ascii=False)
        print(f"Diff report saved to {diff_path}")
        print(f"  Added: {len(diff['added'])} functions")
        print(f"  Modified: {len(diff['modified'])} functions")
        print(f"  Removed: {len(diff['removed'])} functions")

    return final_output_path


def main():
    parser = argparse.ArgumentParser(description="Extract all functions from a C project.")
    parser.add_argument("project_dir", nargs='?', default="ATP_CODE/INIT", help="Root directory of the project")
    parser.add_argument("--types-json", default=".analysis/INIT_global_types.json", help="Path to global_types.json")
    parser.add_argument("--globals-json", default=".analysis/global_variables.json", help="Path to global_variables.json")
    parser.add_argument("--output", "-o", default=".analysis/INIT_functions.json", help="Output JSON file path")
    args = parser.parse_args()
    analyze_project_c_files(args.project_dir, args.types_json, args.globals_json, args.output)

if __name__ == "__main__":
    main()