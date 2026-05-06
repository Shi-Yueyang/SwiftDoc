import json
import os
import argparse

def generate_function_md(functions_json, types_json, figures_dir, output_dir="MD"):
    """
    生成 Markdown 文档。

    Args:
        functions_json: 函数 JSON 文件路径（必填）
        types_json: 类型定义 JSON 文件路径（必填）
        output_dir: MD 文档输出目录（默认 "MD"）
        figures_dir: 调用关系图所在目录（必填，用于生成图片相对路径）
    """

    with open(functions_json, "r", encoding="utf-8") as f:
        func_data = json.load(f)
    functions = func_data.get("functions", [])

    with open(types_json, "r", encoding="utf-8") as f:
        type_data = json.load(f)
    type_defs = type_data.get("type_definitions", {})
    type_refs = type_data.get("type_references", {})

    type_desc_map = {}
    for tname, info in type_defs.items():
        if isinstance(info, dict):
            desc = info.get("type_description", "")
            if desc:
                type_desc_map[tname] = desc

    os.makedirs(output_dir, exist_ok=True)

    for func in functions:
        fname = func.get("name", "unknown_func")
        md_lines = [f"# {fname}", "", f"**function：{fname}**", ""]

        # 输入项表格
        md_lines.append("## 输入项")
        md_lines.append("| 标识符ID | 类型Type | 输入方式Input mode | 数据方向Direction of data | 描述Description |")
        md_lines.append("|----------|----------|--------------------|---------------------------|------------------|")

        inputs = func.get("inputs", [])
        if inputs:
            for inp in inputs:
                name = inp.get("name", "N/A")
                typ = inp.get("type", "N/A")
                mode = "Parameter" if inp.get("kind") == "parameter" else "Global variable"
                direction = inp.get("direction", "in")
                desc = inp.get("inputs_description", "")
                if not desc:
                    desc = "N/A"
                md_lines.append(f"| {name} | {typ} | {mode} | {direction} | {desc} |")
        else:
            md_lines.append("| N/A | N/A | N/A | N/A | N/A |")
        md_lines.append("")

        # 输出项表格
        md_lines.append("## 输出项")
        md_lines.append("| 标识符ID | 类型Type | 输出方式Output mode | 描述Description |")
        md_lines.append("|----------|----------|---------------------|------------------|")

        returns = func.get("returns", [])
        if returns and isinstance(returns, list):
            valid_returns = [ret for ret in returns if ret.get("expression") or ret.get("return_description")]
            if valid_returns:
                for ret in valid_returns:
                    expr = ret.get("expression", "")
                    ret_desc = ret.get("return_description", "")
                    if not ret_desc:
                        ret_desc = "N/A"
                    md_lines.append(f"| {expr} | N/A | Return | {ret_desc} |")
            else:
                md_lines.append("| N/A | N/A | N/A | N/A |")
        else:
            md_lines.append("| N/A | N/A | N/A | N/A |")
        md_lines.append("")

        # 全局数据结构
        global_types = {}
        for inp in inputs:
            if inp.get("kind") == "Global variable":
                typ = inp.get("type", "")
                ref = inp.get("type_ref", "")
                if typ and ref and ref not in ("", "NA", "N/A"):
                    if typ not in global_types:
                        global_types[typ] = ref

        md_lines.append("## 全局数据结构")
        md_lines.append("| 类型Type | 参考Ref | 描述Description |")
        md_lines.append("|----------|---------|------------------|")

        if global_types:
            for typ, ref in global_types.items():
                base_type = typ.split('[')[0].strip()
                base_type = base_type.rstrip('*').strip()
                ref_code = type_refs.get(base_type, ref)
                desc = type_desc_map.get(base_type, "")
                if not desc:
                    desc = "N/A"
                md_lines.append(f"| {typ} | {ref_code} | {desc} |")
        else:
            md_lines.append("| N/A | N/A | N/A |")
        md_lines.append("")

        # 局部数据结构（占位）
        md_lines.append("## 局部数据结构")
        md_lines.append("| 类型Type | 参考Ref | 描述Description |")
        md_lines.append("|----------|---------|------------------|")
        md_lines.append("| N/A | N/A | N/A |")
        md_lines.append("")

        # 算法和逻辑
        algo = func.get("algorithm_logic", "")
        if not algo:
            algo = "无"
        md_lines.append("## 算法和逻辑")
        md_lines.append(algo)
        md_lines.append("")

        # 接口（调用关系图）
        img_name = fname.replace("\\", "_").replace("/", "_").replace(":", "_") + ".png"
        img_abs_path = os.path.join(figures_dir, img_name)
        rel_img_path = os.path.relpath(img_abs_path, start=output_dir)
        md_lines.append("## 接口")
        md_lines.append(f"![]({rel_img_path})")
        md_lines.append("")

        # 保存 MD 文件
        safe_name = fname.replace("\\", "_").replace("/", "_").replace(":", "_")
        md_path = os.path.join(output_dir, f"{safe_name}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成函数文档 Markdown 文件")
    parser.add_argument("--functions-json", required=True, help="函数 JSON 文件路径")
    parser.add_argument("--types-json", required=True, help="类型 JSON 文件路径")
    parser.add_argument("--output-dir", default="MD", help="MD 输出目录（默认 MD）")
    parser.add_argument("--figures-dir", required=True, help="调用关系图所在目录")
    args = parser.parse_args()

    generate_function_md(args.functions_json, args.types_json, args.output_dir, args.figures_dir)