import json
import os
import logging
from collections import defaultdict

from core.utils import iter_progress


logger = logging.getLogger(__name__)


def normalize_function_for_doc(func):
    normalized = dict(func)
    normalized.setdefault("algorithm_logic", "")

    normalized_inputs = []
    for inp in normalized.get("inputs", []):
        if isinstance(inp, dict):
            normalized_input = dict(inp)
            normalized_input.setdefault("inputs_description", "")
            normalized_inputs.append(normalized_input)
    normalized["inputs"] = normalized_inputs

    returns = normalized.get("returns", [])
    if isinstance(returns, list) and returns and isinstance(returns[0], str):
        normalized["returns"] = [
            {"expression": expr, "return_description": ""} for expr in returns
        ]
    else:
        normalized_returns = []
        for ret in returns if isinstance(returns, list) else []:
            if isinstance(ret, dict):
                normalized_return = dict(ret)
                normalized_return.setdefault("expression", "")
                normalized_return.setdefault("return_description", "")
                normalized_returns.append(normalized_return)
        normalized["returns"] = normalized_returns

    return normalized


def _write_function_section(func, type_refs, type_desc_map, figures_dir):
    """Return a list of markdown lines for a single function section."""
    fname = func.get("name", "unknown_func")
    lines = [f"## {fname}", "", f"**function：{fname}**", ""]

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
                lines.append(f"| {expr} | N/A | Return | {ret_desc} |")
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

    # Call graph
    img_name = fname.replace("\\", "_").replace("/", "_").replace(":", "_") + ".png"
    img_abs_path = os.path.join(figures_dir, img_name)
    lines.append("### 接口")
    lines.append(f"![]({img_abs_path})")
    lines.append("")

    return lines


def _load_types(types_json):
    if types_json and os.path.exists(types_json):
        with open(types_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (
            data.get("type_definitions", {}),
            data.get("type_references", {}),
        )
    return {}, {}


def _build_type_desc_map(type_defs):
    return {
        tname: info.get("type_description", "")
        for tname, info in type_defs.items()
        if isinstance(info, dict) and info.get("type_description")
    }


def generate_function_md_per_function(function_list, types_json, figures_dir, output_dir):
    """Generate one .md file per function."""
    type_defs, type_refs = _load_types(types_json)
    type_desc_map = _build_type_desc_map(type_defs)
    os.makedirs(output_dir, exist_ok=True)

    for _, _, raw_func in iter_progress(function_list, "Generating markdown"):
        func = normalize_function_for_doc(raw_func)
        fname = func.get("name", "unknown_func")
        lines = [f"# {fname}", ""]
        lines += _write_function_section(func, type_refs, type_desc_map, figures_dir)[1:]  # skip the ## header

        safe_name = fname.replace("\\", "_").replace("/", "_").replace(":", "_")
        with open(os.path.join(output_dir, f"{safe_name}.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


def generate_function_md_by_file(function_list, types_json, figures_dir, output_dir):
    """Generate one .md file per source file, grouping functions together."""
    type_defs, type_refs = _load_types(types_json)
    type_desc_map = _build_type_desc_map(type_defs)
    os.makedirs(output_dir, exist_ok=True)

    grouped = defaultdict(list)
    for func in function_list:
        grouped[func.get("file", "unknown")].append(func)

    items = list(grouped.items())
    for _, _, (file_path, funcs) in iter_progress(items, "Generating markdown"):
        base = os.path.splitext(os.path.basename(file_path))[0]
        safe_base = base.replace("\\", "_").replace("/", "_").replace(":", "_")

        lines = [f"# {base}.c", f"", f"**Source file: {file_path}**", "", f"Functions: {len(funcs)}", ""]

        for raw_func in funcs:
            func = normalize_function_for_doc(raw_func)
            lines += _write_function_section(func, type_refs, type_desc_map, figures_dir)
            lines.append("---")
            lines.append("")

        with open(os.path.join(output_dir, f"{safe_base}.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


def generate_function_md(functions_json=None, function_list=None, types_json=None,
                         figures_dir=None, output_dir="MD", group_by="function"):
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
        generate_function_md_by_file(functions, types_json, figures_dir, output_dir)
    else:
        generate_function_md_per_function(functions, types_json, figures_dir, output_dir)
