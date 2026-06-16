import json
import os
import logging
from collections import defaultdict

from core.utils import iter_progress
from generators.common import normalize_function_for_doc, load_types, build_type_desc_map


logger = logging.getLogger(__name__)


def _write_function_section(func, type_refs, type_desc_map, figures_dir, style="plain"):
    """Return a list of markdown lines for a single function section."""
    fname = func.get("name", "unknown_func")
    lines = [f"## {fname}", "", f"**function：{fname}**", ""]

    # 模块描述
    file_path = func.get("file", "unknown")
    start_line = func.get("start_line", 0)
    lines.append("### 模块描述")
    lines.append("")
    lines.append(f"**函数名 Function name:** {fname}")
    lines.append("")
    lines.append(f"**文件名 File name:** {file_path}")
    lines.append("")
    lines.append(f"**行号 Line number:** {start_line}")
    lines.append("")

    inputs = func.get("inputs", [])

    # Input table
    lines.append("### 输入项")
    lines.append("| 标识符ID | 类型Type | 输入方式Input mode | 数据方向Direction of data | 描述Description |")
    lines.append("|----------|----------|--------------------|---------------------------|------------------|")
    if inputs:
        for inp in inputs:
            name = inp.get("name", "N/A")
            typ = inp.get("type", "N/A")
            mode = "Parameter" if inp.get("kind") == "parameter" else "Global variable"
            direction = inp.get("direction", "in")
            desc = inp.get("inputs_description", "") or "N/A"
            lines.append(f"| {name} | {typ} | {mode} | {direction} | {desc} |")
    else:
        lines.append("| N/A | N/A | N/A | N/A | N/A |")
    lines.append("")

    # Output table
    lines.append("### 输出项")
    lines.append("| 标识符ID | 类型Type | 输出方式Output mode | 描述Description |")
    lines.append("|----------|----------|---------------------|------------------|")
    returns = func.get("returns", [])
    if returns and isinstance(returns, list):
        valid_returns = [ret for ret in returns if ret.get("expression") or ret.get("return_description")]
        if valid_returns:
            for ret in valid_returns:
                expr = ret.get("expression", "")
                ret_desc = ret.get("return_description", "") or "N/A"
                ret_type = func.get("return_type", "") or "N/A"
                lines.append(f"| {expr} | {ret_type} | Return | {ret_desc} |")
        else:
            lines.append("| N/A | N/A | N/A | N/A |")
    else:
        lines.append("| N/A | N/A | N/A | N/A |")
    lines.append("")

    # Global data structures
    global_types = {}
    for inp in inputs:
        if inp.get("kind") == "Global variable":
            typ = inp.get("type", "")
            ref = inp.get("type_ref", "")
            if typ and ref and ref not in ("", "NA", "N/A"):
                if typ not in global_types:
                    global_types[typ] = ref

    lines.append("### 全局数据结构")
    lines.append("| 类型Type | 参考Ref | 描述Description |")
    lines.append("|----------|---------|------------------|")
    if global_types:
        for typ, ref in global_types.items():
            base_type = typ.split("[")[0].strip().rstrip("*").strip()
            ref_code = type_refs.get(base_type, ref)
            desc = type_desc_map.get(base_type, "") or "N/A"
            lines.append(f"| {typ} | {ref_code} | {desc} |")
    else:
        lines.append("| N/A | N/A | N/A |")
    lines.append("")

    # Local data structures (placeholder)
    lines.append("### 局部数据结构")
    lines.append("| 类型Type | 参考Ref | 描述Description |")
    lines.append("|----------|---------|------------------|")
    lines.append("| N/A | N/A | N/A |")
    lines.append("")

    # Algorithm
    algo = func.get("algorithm_logic", "")
    lines.append("### 算法和逻辑")
    lines.append(algo)
    lines.append("")

    # Call graph / table
    lines.append("### 接口")
    if style == "table":
        callers = [c for c in func.get("called_by", []) if c != fname]
        callees = [c for c in func.get("calls", []) if c != fname]
        lines.append("| Callers | Callees |")
        lines.append("|---------|---------|")
        max_rows = max(len(callers), len(callees), 1)
        for i in range(max_rows):
            c1 = callers[i] if i < len(callers) else ""
            c2 = callees[i] if i < len(callees) else ""
            lines.append(f"| {c1} | {c2} |")
    else:
        img_name = fname.replace("\\", "_").replace("/", "_").replace(":", "_") + ".png"
        img_abs_path = os.path.join(figures_dir, img_name)
        lines.append(f"![]({img_abs_path})")
    lines.append("")

    return lines


def generate_function_md_per_function(function_list, types_json, figures_dir, output_dir,
                                     style="plain"):
    """Generate one .md file per function."""
    type_defs, type_refs = load_types(types_json)
    type_desc_map = build_type_desc_map(type_defs)
    os.makedirs(output_dir, exist_ok=True)

    for _, _, raw_func in iter_progress(function_list, "Generating markdown"):
        func = normalize_function_for_doc(raw_func)
        fname = func.get("name", "unknown_func")
        lines = [f"# {fname}", ""]
        lines += _write_function_section(func, type_refs, type_desc_map, figures_dir, style=style)[1:]

        safe_name = fname.replace("\\", "_").replace("/", "_").replace(":", "_")
        with open(os.path.join(output_dir, f"{safe_name}.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


def generate_function_md_by_file(function_list, types_json, figures_dir, output_dir,
                                 style="plain"):
    """Generate one .md file per source file, grouping functions together."""
    type_defs, type_refs = load_types(types_json)
    type_desc_map = build_type_desc_map(type_defs)
    os.makedirs(output_dir, exist_ok=True)

    grouped = defaultdict(list)
    for func in function_list:
        grouped[func.get("file", "unknown")].append(func)

    items = list(grouped.items())
    for _, _, (file_path, funcs) in iter_progress(items, "Generating markdown"):
        base = os.path.splitext(os.path.basename(file_path))[0]
        safe_base = base.replace("\\", "_").replace("/", "_").replace(":", "_")

        filename = os.path.basename(file_path)
        lines = [f"# {filename}", f"", f"**Source file: {file_path}**", "", f"Functions: {len(funcs)}", ""]

        for raw_func in funcs:
            func = normalize_function_for_doc(raw_func)
            lines += _write_function_section(func, type_refs, type_desc_map, figures_dir, style=style)
            lines.append("---")
            lines.append("")

        with open(os.path.join(output_dir, f"{safe_base}.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


def generate_function_md(functions_json=None, function_list=None, types_json=None,
                         figures_dir=None, output_dir="MD", group_by="function",
                         style="plain"):
    if function_list is not None:
        functions = function_list
    else:
        if functions_json is None:
            raise ValueError("Either functions_json or function_list must be provided")
        with open(functions_json, "r", encoding="utf-8") as f:
            func_data = json.load(f)
        functions = func_data.get("functions", [])

    if types_json is None:
        raise ValueError("types_json must be provided")
    if figures_dir is None:
        raise ValueError("figures_dir must be provided")

    if group_by == "file":
        generate_function_md_by_file(functions, types_json, figures_dir, output_dir, style=style)
    else:
        generate_function_md_per_function(functions, types_json, figures_dir, output_dir, style=style)
