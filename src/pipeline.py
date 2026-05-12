import os
import json

from extract_globals import extract_all_globals
from extract_types import collect_all_types_from_project
from image_generator import generate_function_graphs
from md_generator import generate_function_md
from appendix_generate import generate_appendix_md
from version_diff import update_master_from_diff
from module_analysis import (
    analyze_project_c_files
)


def run_extract_phase(args):
    print("Scanning root dir...")
    os.makedirs(args.cache_dir, exist_ok=True)
    enable_ai = getattr(args, "ai", "on") == "on"

    source_path = os.path.normpath(args.source_dir)
    if os.path.isfile(source_path) and source_path.endswith('.c'):
        project_root = os.path.dirname(source_path)
        file_filter = source_path

    else:
        project_root = source_path
        file_filter = None

    folder_name = os.path.basename(os.path.normpath(args.source_dir))

    # 1. 全局变量
    globals_json = os.path.join(args.cache_dir, f"{folder_name}_global_variables.json")
    globals_list = extract_all_globals(project_root)
    with open(globals_json, 'w', encoding='utf-8') as f:
        json.dump({"globals": globals_list}, f, indent=2, ensure_ascii=False)
    print(f"  Saved {len(globals_list)} global variables -> {globals_json}")

    # 2. 类型定义（调用AI生成类型描述）
    types_json = os.path.join(args.cache_dir, f"{folder_name}_global_types.json")
    new_types_path = collect_all_types_from_project(
        project_root,
        args.cache_dir,
        enable_ai=enable_ai,
        enable_version_control=True,
    )
    diff_json_path = os.path.join(os.path.dirname(new_types_path), "types_diff.json")
    if os.path.exists(diff_json_path):
        update_master_from_diff(types_json, diff_json_path, enable_ai=enable_ai)
        print(f"  Master types JSON updated from diff.")
    else:
        print(f"  No types_diff.json found, skipping update.")

    if not enable_ai:
        print("  AI is disabled; type descriptions will not be generated during extract.")

    # 3. 函数签名（不调用函数AI）
    functions_json = os.path.join(args.cache_dir, f"{folder_name}_functions.json")
    analyze_project_c_files(
        project_dir=project_root,
        types_json_path=types_json,
        globals_json_path=globals_json,
        output_json_path=functions_json,
        enable_ai=False,
        enable_version_control=True,
        file_filter=file_filter  
    )
    print(f"  Saved function signatures -> {functions_json}")

    print("[Extract] Phase completed. You can now run 'docgen' for specific modules.")


def run_docgen_phase(args):
    """文档生成阶段：仅使用 diff 增量更新（只对 module_dir 下的变化函数调用 AI）"""
    print("[DocGen] Loading cached analysis data...")
    cache_dir = args.cache_dir
    source_dir = args.source_dir
    module_dir = args.module_dir
    output_folder = args.output_folder
    enable_ai = (args.ai == "on")

    source_path = os.path.normpath(source_dir)
    if os.path.isfile(source_path) and source_path.endswith('.c'):
        project_root = os.path.dirname(source_path)
    else:
        project_root = source_path
    folder_name = os.path.basename(os.path.normpath(project_root))
    globals_json = os.path.join(cache_dir, f"{folder_name}_global_variables.json")
    types_json = os.path.join(cache_dir, f"{folder_name}_global_types.json")
    functions_json = os.path.join(cache_dir, f"{folder_name}_functions.json")
    functions_diff_json = os.path.join(cache_dir, "functions_diff.json")

    # 1. 加载类型和全局变量数据
    with open(globals_json, 'r', encoding='utf-8') as f:
        all_globals = {g["name"]: g for g in json.load(f).get("globals", [])}

    with open(types_json, 'r', encoding='utf-8') as f:
        types_data = json.load(f)
        all_types = types_data.get("type_definitions", {})
        type_refs = types_data.get("type_references", {})

    # 2. 处理函数数据：优先使用 diff 增量更新，否则直接加载
    diff_exists = os.path.exists(functions_diff_json)
    if enable_ai and diff_exists:
        print(f"  检测到差异文件 {functions_diff_json}，使用增量 AI 更新模式（仅模块 {module_dir}）")
        from version_diff import update_master_from_diff_functions
        # 只处理 module_dir 下的变化函数
        updated = update_master_from_diff_functions(
            functions_json, functions_diff_json,
            target_dir=module_dir,   
            enable_ai=True
        )
        if updated:
            with open(functions_json, 'r', encoding='utf-8') as f:
                all_functions = json.load(f).get("functions", [])
        else:
            print("  没有需要更新的函数变化，直接加载现有数据。")
            with open(functions_json, 'r', encoding='utf-8') as f:
                all_functions = json.load(f).get("functions", [])
    else:
        with open(functions_json, 'r', encoding='utf-8') as f:
            all_functions = json.load(f).get("functions", [])
        if enable_ai and not diff_exists:
            print("  未找到差异文件，跳过 AI 更新。")

    # 3. 筛选属于 module_dir 的函数（用于生成文档）
    module_norm = os.path.normpath(module_dir)
    selected_funcs = []
    for func in all_functions:
        func_file = os.path.normpath(func["file"])
        if os.path.isfile(module_norm) and module_norm.endswith('.c'):
            if func_file == module_norm:
                selected_funcs.append(func)
        else:
            if func_file.startswith(module_norm):
                selected_funcs.append(func)

    if not selected_funcs:
        print(f"Warning: No functions found under {module_dir}")
        return

    print(f"  Selected {len(selected_funcs)} functions from {module_dir}")

    # 4. 如果未启用 AI，为选中的函数填充空字段（避免生成文档时报错）
    if not enable_ai:
        for func in selected_funcs:
            func.setdefault("algorithm_logic", "")
            if isinstance(func.get('returns'), list) and func['returns'] and isinstance(func['returns'][0], str):
                func['returns'] = [{"expression": expr, "return_description": ""} for expr in func['returns']]
            else:
                for ret in func.get('returns', []):
                    if isinstance(ret, dict):
                        ret.setdefault("return_description", "")
            for inp in func.get("inputs", []):
                inp.setdefault("inputs_description", "")

    # 5. 生成图表和文档
    used_type_names = set()
    for func in selected_funcs:
        for inp in func.get("inputs", []):
            if inp.get("kind") == "Global variable":
                base_type = inp["type"].split(' ')[-1]
                used_type_names.add(base_type)
            param_type = inp.get("type", "")
            for word in param_type.split():
                if word in type_refs:
                    used_type_names.add(word)

    figures_dir = os.path.join(output_folder, "figures")
    generate_function_graphs(function_list=selected_funcs, output_dir=figures_dir)

    generate_function_md(
        functions_json=None,
        function_list=selected_funcs,
        types_json=types_json,
        figures_dir=figures_dir,
        output_dir=output_folder
    )

    appendix_output = os.path.join(output_folder, "appendix.md")
    generate_appendix_md(types_json, appendix_output, filter_types=None)

    print(f"[DocGen] Documentation generated in {output_folder}")

