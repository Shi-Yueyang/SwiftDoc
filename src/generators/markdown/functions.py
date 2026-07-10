import os
import logging
from collections import defaultdict

from core.utils import iter_progress
from generators.common import normalize_function_for_doc, load_types, build_type_desc_map, _extract_base_type_name


logger = logging.getLogger(__name__)


def _write_function_section(func, type_refs, type_desc_map, figures_dir, style="plain", sections=None, out_param_location="inputs"):
    """Return a list of markdown lines for a single function section."""
    if sections is None:
        sections = {}
    fname = func.get("name", "unknown_func")
    lines = [f"## {fname}", "", f"**function：{fname}**", ""]

    # 模块描述
    if sections.get("module_description", True):
        file_path = func.get("file", "unknown")
        start_line = func.get("start_line", 0)
        lines.append("### 模块描述")
        lines.append("")
        lines.append(f"**函数名 Function name:** {fname}")
        lines.append("")
        lines.append(f"**文件名 File name:** {os.path.basename(file_path)}")
        lines.append("")
        lines.append(f"**行号 Line number:** {start_line}")
        lines.append("")

        cond_macros = func.get("conditional_macros", [])
        if cond_macros:
            lines.append("**宏列表 Macro list:**")
            for macro in cond_macros:
                lines.append(f"- {macro}")
        else:
            lines.append("**宏列表 Macro list:**")
        lines.append("")

    # 模块功能
    if sections.get("module_summary", True):
        summary = func.get("module_summary", "")
        lines.append("### 模块功能")
        lines.append("")
        lines.append(summary if summary else "N/A")
        lines.append("")

    inputs = func.get("inputs", [])

    # Input table
    if sections.get("inputs", True):
        lines.append("### 输入项")
        lines.append("| 标识符ID | 类型Type | 输入方式Input mode | 数据方向Direction of data | 描述Description |")
        lines.append("|----------|----------|--------------------|---------------------------|------------------|")
        display_inputs = inputs
        if out_param_location == "outputs":
            display_inputs = [inp for inp in inputs if inp.get("direction") != "out"]
        if display_inputs:
            for inp in display_inputs:
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
    if sections.get("outputs", True):
        lines.append("### 输出项")
        lines.append("| 标识符ID | 类型Type | 输出方式Output mode | 描述Description |")
        lines.append("|----------|----------|---------------------|------------------|")
        returns = func.get("returns", [])
        out_params = [inp for inp in inputs if inp.get("direction") == "out"] if out_param_location == "outputs" else []
        has_returns = returns and isinstance(returns, list)
        valid_returns = [ret for ret in returns if ret.get("expression") or ret.get("return_description")] if has_returns else []
        if valid_returns or out_params:
            for ret in valid_returns:
                expr = ret.get("expression", "")
                ret_desc = ret.get("return_description", "") or "N/A"
                ret_type = func.get("return_type", "") or "N/A"
                lines.append(f"| {expr} | {ret_type} | Return | {ret_desc} |")
            for inp in out_params:
                name = inp.get("name", "N/A")
                typ = inp.get("type", "N/A")
                desc = inp.get("inputs_description", "") or "N/A"
                lines.append(f"| {name} | {typ} | out parameter | {desc} |")
        else:
            lines.append("| N/A | N/A | N/A | N/A |")
        lines.append("")

    # Global data structures
    if sections.get("global_data", True):
        global_types = {}
        for inp in inputs:
            typ = inp.get("type", "")
            ref = inp.get("type_ref", "")
            if typ and ref and ref not in ("", "NA", "N/A"):
                base_type = _extract_base_type_name(typ)
                if base_type in type_refs and typ not in global_types:
                    global_types[typ] = ref
        # Also include the return type if it references a known global type
        return_type = func.get("return_type", "")
        if return_type:
            base_type = _extract_base_type_name(return_type)
            if base_type in type_refs and return_type not in global_types:
                global_types[return_type] = type_refs[base_type]


        lines.append("### 全局数据结构")
        lines.append("| 类型Type | 参考Ref | 描述Description |")
        lines.append("|----------|---------|------------------|")
        if global_types:
            for typ, ref in global_types.items():
                base_type = _extract_base_type_name(typ)
                ref_code = type_refs.get(base_type, ref)
                desc = type_desc_map.get(base_type, "") or "N/A"
                lines.append(f"| {base_type} | {ref_code} | {desc} |")
        else:
            lines.append("| N/A | N/A | N/A |")
        lines.append("")

    # Local data structures (placeholder)
    if sections.get("local_data", True):
        lines.append("### 局部数据结构")
        lines.append("| 类型Type | 参考Ref | 描述Description |")
        lines.append("|----------|---------|------------------|")
        lines.append("| N/A | N/A | N/A |")
        lines.append("")

    # Algorithm
    if sections.get("algorithm", True):
        algo = func.get("algorithm_logic", "")
        lines.append("### 算法和逻辑")
        lines.append(algo)
        lines.append("")

    # Call graph / table
    if sections.get("interface", True):
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
                                     style="plain", sections=None, embedded_global_reference=False, language="c",
                                     out_param_location="inputs"):
    """Generate one .md file per function."""
    type_defs, type_refs = load_types(types_json)
    type_desc_map = build_type_desc_map(type_defs)
    os.makedirs(output_dir, exist_ok=True)

    for _, _, raw_func in iter_progress(function_list, "Generating markdown"):
        func = normalize_function_for_doc(raw_func)

        # -- embedded type-ref renumbering --
        if embedded_global_reference:
            from generators.common import build_embedded_type_refs
            embedded_type_refs, embedded_ref_to_type = build_embedded_type_refs([raw_func], type_refs)
        else:
            embedded_type_refs = type_refs
            embedded_ref_to_type = {}

        fname = func.get("name", "unknown_func")
        lines = [f"# {fname}", ""]
        lines += _write_function_section(func, embedded_type_refs, type_desc_map, figures_dir, style=style,
                                         sections=sections, out_param_location=out_param_location)[1:]

        # -- embedded appendix --
        if embedded_global_reference and embedded_ref_to_type:
            from generators.markdown.appendix import generate_embedded_appendix_md
            lines += generate_embedded_appendix_md(type_defs, embedded_ref_to_type, language)

        safe_name = fname.replace("\\", "_").replace("/", "_").replace(":", "_")
        with open(os.path.join(output_dir, f"{safe_name}.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


def generate_function_md_by_file(function_list, types_json, figures_dir, output_dir,
                                 style="plain", sections=None, embedded_global_reference=False, language="c",
                                 out_param_location="inputs"):
    """Generate one .md file per source file, grouping functions together."""
    type_defs, type_refs = load_types(types_json)
    type_desc_map = build_type_desc_map(type_defs)
    os.makedirs(output_dir, exist_ok=True)

    grouped = defaultdict(list)
    for func in function_list:
        grouped[func.get("file", "unknown")].append(func)

    items = list(grouped.items())
    for _, _, (file_path, funcs) in iter_progress(items, "Generating markdown"):
        # -- local type-ref renumbering --
        if embedded_global_reference:
            from generators.common import build_embedded_type_refs
            embedded_type_refs, embedded_ref_to_type = build_embedded_type_refs(funcs, type_refs)
        else:
            embedded_type_refs = type_refs
            embedded_ref_to_type = {}

        base = os.path.splitext(os.path.basename(file_path))[0]
        safe_base = base.replace("\\", "_").replace("/", "_").replace(":", "_")

        filename = os.path.basename(file_path)
        lines = [f"# {filename}", f"", f"**Source file: {filename}**", "", f"Functions: {len(funcs)}", ""]

        for raw_func in funcs:
            func = normalize_function_for_doc(raw_func)
            lines += _write_function_section(func, embedded_type_refs, type_desc_map, figures_dir, style=style,
                                             sections=sections, out_param_location=out_param_location)
            lines.append("---")
            lines.append("")

        # -- embedded appendix --
        if embedded_global_reference and embedded_ref_to_type:
            from generators.markdown.appendix import generate_embedded_appendix_md
            lines += generate_embedded_appendix_md(type_defs, embedded_ref_to_type, language)

        with open(os.path.join(output_dir, f"{safe_base}.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


def generate_function_md(function_list, types_json, figures_dir, output_dir="MD",
                         group_by="function", style="plain", sections=None,
                         embedded_global_reference=False, language="c", out_param_location="inputs"):
    functions = function_list

    if group_by == "file":
        generate_function_md_by_file(functions, types_json, figures_dir, output_dir, style=style,
                                     sections=sections, embedded_global_reference=embedded_global_reference, language=language,
                                     out_param_location=out_param_location)
    else:
        generate_function_md_per_function(functions, types_json, figures_dir, output_dir, style=style,
                                          sections=sections, embedded_global_reference=embedded_global_reference, language=language,
                                          out_param_location=out_param_location)
