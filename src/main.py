#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Integrated C/C++ code analysis tool.
Extracts global variables, type definitions, function signatures, generates call graphs and Markdown documentation.
"""

import os
import sys
import argparse
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from extract_globals import extract_all_globals
from extract_types import collect_all_types_from_project
from module_analysis import analyze_project_c_files
from image_generator import generate_function_graphs
from md_generator import generate_function_md
from appendix_generate import generate_appendix_md

def main():
    parser = argparse.ArgumentParser(
        description="Integrated C/C++ analysis: extract globals, types, functions, generate call graphs and MD docs."
    )

    parser.add_argument("source_dir", nargs='?', default="ATP_CODE/INIT",
                        help="Root directory of the C/C++ project (default: ATP_CODE)")
    #中间结果存放目录
    parser.add_argument("--cache-dir", "--output", "-o", dest="cache_dir", default=".analysis",
                        help="Intermediate cache directory for generated analysis files (default: .analysis)")
    parser.add_argument("--ai", choices=["on", "off"], default="on",
                        help="Enable or disable AI analysis: on|off (default: on)")
    parser.add_argument("--output_format", choices=["md"], default="md",
                        help="Output format (currently only: md)")
    parser.add_argument("--output_folder", default="MD",
                        help="Output folder for generated Markdown files (default: MD)")

    args = parser.parse_args()
    enable_ai = args.ai == "on"

    os.makedirs(args.cache_dir, exist_ok=True)

    folder_name = os.path.basename(os.path.normpath(args.source_dir))

    globals_json = os.path.join(args.cache_dir, f"{folder_name}_global_variables.json")
    types_json = os.path.join(args.cache_dir, f"{folder_name}_global_types.json")
    functions_json = os.path.join(args.cache_dir, f"{folder_name}_functions.json")
    figures_dir = os.path.join(args.cache_dir, "figures")

    # 1. 提取全局变量
    print("\n[Step 1] Extracting global variables...")
    globals_list = extract_all_globals(args.source_dir)
    with open(globals_json, 'w', encoding='utf-8') as f:
        json.dump({"globals": globals_list}, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(globals_list)} global variables to {globals_json}")

    # 2. 提取类型定义（并调用 AI 描述）
    print("\n[Step 2] Extracting type definitions...")
    collect_all_types_from_project(args.source_dir, args.cache_dir, enable_ai=enable_ai)

    # 3. 分析函数（提取输入、输出、调用关系，并调用 AI 描述）
    print("\n[Step 3] Analyzing functions...")
    analyze_project_c_files(
        project_dir=args.source_dir,
        types_json_path=types_json,
        globals_json_path=globals_json,
        output_json_path=functions_json,
        enable_ai=enable_ai
    )

    # 4. 生成调用关系图
    print("\n[Step 4] Generating call graphs...")
    generate_function_graphs(functions_json, figures_dir)

    # 5. 生成 Markdown 文档
    print("\n[Step 5] Generating Markdown documentation...")
    # 函数文档
    generate_function_md(
        functions_json=functions_json,
        types_json=types_json,
        figures_dir=figures_dir,
        output_dir=args.output_folder
    )
    # 附录（全局数据结构表格）
    if os.path.exists(types_json):
        appendix_output = os.path.join(args.output_folder, "appendix.md")
        generate_appendix_md(types_json, appendix_output)
    else:
        print("Warning: types_json not found, skipping appendix generation.")

    print("\n✅ All tasks completed successfully.")

if __name__ == "__main__":
    main()