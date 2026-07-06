import os
import logging
from collections import defaultdict

from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from core.utils import iter_progress
from generators.common import normalize_function_for_doc, load_types, build_type_desc_map, _extract_base_type_name

logger = logging.getLogger(__name__)

HEADER_SHADING = "D9E2F3"


def _create_document():
    doc = Document()

    section = doc.sections[0]
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(3.17)
    section.right_margin = Cm(3.17)

    style = doc.styles["Normal"]
    font = style.font
    font.name = "Calibri"
    font.size = Pt(10.5)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")

    for level, size in [(1, 16), (2, 13), (3, 11)]:
        heading_style = doc.styles[f"Heading {level}"]
        heading_style.font.size = Pt(size)
        heading_style.font.bold = True
        heading_style.font.name = "Calibri"
        heading_style.element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")

    return doc


def _set_cell_shading(cell, color):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), color)
    shading.set(qn("w:val"), "clear")
    tcPr.append(shading)


def _set_cell_text(cell, text, bold=False):
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run(str(text) if text is not None else "")
    run.font.size = Pt(9)
    run.font.name = "Calibri"
    run.bold = bold


def _style_header_row(table, headers):
    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        _set_cell_text(cell, header, bold=True)
        _set_cell_shading(cell, HEADER_SHADING)


def _add_input_table(doc, inputs, heading_level):
    doc.add_heading("输入项", level=heading_level)
    table = doc.add_table(rows=1, cols=5)
    table.style = "Table Grid"
    _style_header_row(table, [
        "标识符ID", "类型Type", "输入方式Input mode",
        "数据方向Direction of data", "描述Description",
    ])

    if inputs:
        for inp in inputs:
            row = table.add_row()
            _set_cell_text(row.cells[0], inp.get("name", "N/A"))
            _set_cell_text(row.cells[1], inp.get("type", "N/A"))
            mode = "Parameter" if inp.get("kind") == "parameter" else "Global variable"
            _set_cell_text(row.cells[2], mode)
            _set_cell_text(row.cells[3], inp.get("direction", "in"))
            _set_cell_text(row.cells[4], inp.get("inputs_description") or "N/A")
    else:
        row = table.add_row()
        for cell in row.cells:
            _set_cell_text(cell, "N/A")

    doc.add_paragraph()


def _add_output_table(doc, returns, heading_level, return_type="", out_params=None):
    doc.add_heading("输出项", level=heading_level)
    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    _style_header_row(table, [
        "标识符ID", "类型Type", "输出方式Output mode", "描述Description",
    ])

    ret_type_text = return_type or "N/A"
    if out_params is None:
        out_params = []
    has_returns = returns and isinstance(returns, list)
    valid_returns = [r for r in returns if r.get("expression") or r.get("return_description")] if has_returns else []
    if valid_returns or out_params:
        for ret in valid_returns:
            row = table.add_row()
            _set_cell_text(row.cells[0], ret.get("expression", ""))
            _set_cell_text(row.cells[1], ret_type_text)
            _set_cell_text(row.cells[2], "Return")
            _set_cell_text(row.cells[3], ret.get("return_description", "") or "N/A")
        for inp in out_params:
            row = table.add_row()
            _set_cell_text(row.cells[0], inp.get("name", "N/A"))
            _set_cell_text(row.cells[1], inp.get("type", "N/A"))
            _set_cell_text(row.cells[2], "out parameter")
            _set_cell_text(row.cells[3], inp.get("inputs_description", "") or "N/A")
    else:
        row = table.add_row()
        for cell in row.cells:
            _set_cell_text(cell, "N/A")

    doc.add_paragraph()


def _add_global_data_table(doc, inputs, type_refs, type_desc_map, heading_level,
                          return_type=""):
    global_types = {}
    # Collect from inputs (parameters + global variables)
    for inp in inputs:
        typ = inp.get("type", "")
        ref = inp.get("type_ref", "")
        if typ and ref and ref not in ("", "NA", "N/A"):
            base_type = _extract_base_type_name(typ)
            if base_type in type_refs and typ not in global_types:
                global_types[typ] = ref
    # Also include the return type if it references a known global type
    if return_type:
        base_type = _extract_base_type_name(return_type)
        if base_type in type_refs and return_type not in global_types:
            global_types[return_type] = type_refs[base_type]

    doc.add_heading("全局数据结构", level=heading_level)
    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    _style_header_row(table, ["类型Type", "参考Ref", "描述Description"])

    if global_types:
        for typ, ref in global_types.items():
            row = table.add_row()
            _set_cell_text(row.cells[0], base_type)
            base_type = _extract_base_type_name(typ)
            ref_code = type_refs.get(base_type, ref)
            _set_cell_text(row.cells[1], ref_code)
            desc = type_desc_map.get(base_type, "") or "N/A"
            _set_cell_text(row.cells[2], desc)
    else:
        row = table.add_row()
        for cell in row.cells:
            _set_cell_text(cell, "N/A")

    doc.add_paragraph()


def _add_local_data_table(doc, heading_level):
    doc.add_heading("局部数据结构", level=heading_level)
    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    _style_header_row(table, ["类型Type", "参考Ref", "描述Description"])

    row = table.add_row()
    for cell in row.cells:
        _set_cell_text(cell, "N/A")

    doc.add_paragraph()


def _add_algorithm_section(doc, algo, heading_level):
    doc.add_heading("算法和逻辑", level=heading_level)
    doc.add_paragraph(algo or "")
    doc.add_paragraph()


def _add_call_graph(doc, func, fname, figures_dir, heading_level, style="plain"):
    doc.add_heading("接口", level=heading_level)
    if style == "table":
        callers = [c for c in func.get("called_by", []) if c != fname]
        callees = [c for c in func.get("calls", []) if c != fname]
        max_rows = max(len(callers), len(callees), 1)
        table = doc.add_table(rows=max_rows + 1, cols=2)
        table.style = "Table Grid"
        _style_header_row(table, ["Callers", "Callees"])
        for i in range(max_rows):
            row = table.rows[i + 1]
            _set_cell_text(row.cells[0], callers[i] if i < len(callers) else "")
            _set_cell_text(row.cells[1], callees[i] if i < len(callees) else "")
    else:
        safe_name = fname.replace("\\", "_").replace("/", "_").replace(":", "_")
        img_path = os.path.join(figures_dir, f"{safe_name}.png")
        if os.path.exists(img_path):
            try:
                doc.add_picture(img_path, width=Inches(5.5))
                last_paragraph = doc.paragraphs[-1]
                last_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            except Exception:
                logger.debug("Failed to embed image: %s", img_path)
    doc.add_paragraph()


def _add_function_section(doc, func, type_refs, type_desc_map, figures_dir, heading_level,
                         style="plain", sections=None, out_param_location="inputs"):
    if sections is None:
        sections = {}
    fname = func.get("name", "unknown_func")
    doc.add_heading(fname, level=heading_level)

    p = doc.add_paragraph()
    run = p.add_run(f"function：{fname}")
    run.bold = True

    # 模块描述
    if sections.get("module_description", True):
        doc.add_heading("模块描述", level=heading_level + 1)
        file_path = func.get("file", "unknown")
        start_line = func.get("start_line", 0)

        p = doc.add_paragraph()
        run = p.add_run("ModuleName<")
        p.add_run(f"{fname}>")

        p = doc.add_paragraph()
        run = p.add_run("FileName<")
        p.add_run(f"{os.path.basename(file_path)}>")

        p = doc.add_paragraph()
        run = p.add_run("LineNumber<")
        p.add_run(f"{start_line}>")

        cond_macros = func.get("conditional_macros", [])
        p = doc.add_paragraph()
        run = p.add_run("MacroNameList<")
        p.add_run(",".join(cond_macros))
        p.add_run(">")

    if sections.get("module_summary", True):
        doc.add_heading("模块功能", level=heading_level + 1)
        summary = func.get("module_summary", "")
        doc.add_paragraph(summary if summary else "N/A")
        doc.add_paragraph()

    if sections.get("inputs", True):
        all_inputs = func.get("inputs", [])
        display_inputs = all_inputs
        if out_param_location == "outputs":
            display_inputs = [inp for inp in all_inputs if inp.get("direction") != "out"]
        _add_input_table(doc, display_inputs, heading_level + 1)
    if sections.get("outputs", True):
        out_params = [inp for inp in func.get("inputs", []) if inp.get("direction") == "out"] if out_param_location == "outputs" else []
        _add_output_table(doc, func.get("returns", []), heading_level + 1,
                          return_type=func.get("return_type", ""), out_params=out_params)
    if sections.get("global_data", True):
        _add_global_data_table(doc, func.get("inputs", []), type_refs, type_desc_map,
                              heading_level + 1,
                              return_type=func.get("return_type", ""))
    if sections.get("local_data", True):
        _add_local_data_table(doc, heading_level + 1)
    if sections.get("algorithm", True):
        _add_algorithm_section(doc, func.get("algorithm_logic", ""), heading_level + 1)
    if sections.get("interface", True):
        _add_call_graph(doc, func, fname, figures_dir, heading_level + 1, style=style)


def _sanitize_filename(name):
    return name.replace("\\", "_").replace("/", "_").replace(":", "_")


def generate_function_docx_per_function(function_list, types_json, figures_dir, output_dir,
                                        style="plain", sections=None, local_table=False, language="c",
                                        out_param_location="inputs"):
    type_defs, type_refs = load_types(types_json)
    type_desc_map = build_type_desc_map(type_defs)
    os.makedirs(output_dir, exist_ok=True)

    for _, _, raw_func in iter_progress(function_list, "Generating docx"):
        func = normalize_function_for_doc(raw_func)

        # -- local type-ref renumbering --
        if local_table:
            from generators.common import build_local_type_refs
            local_type_refs, local_ref_to_type = build_local_type_refs([raw_func], type_refs)
        else:
            local_type_refs = type_refs
            local_ref_to_type = {}

        fname = func.get("name", "unknown_func")
        doc = _create_document()
        _add_function_section(doc, func, local_type_refs, type_desc_map, figures_dir, heading_level=1,
                              style=style, sections=sections, out_param_location=out_param_location)

        # -- local appendix --
        if local_table and local_ref_to_type:
            from generators.docx.appendix import _add_local_appendix_docx
            _add_local_appendix_docx(doc, type_defs, local_ref_to_type, language)

        safe_name = _sanitize_filename(fname)
        doc.save(os.path.join(output_dir, f"{safe_name}.docx"))


def generate_function_docx_by_file(function_list, types_json, figures_dir, output_dir,
                                   style="plain", sections=None, local_table=False, language="c",
                                   out_param_location="inputs"):
    type_defs, type_refs = load_types(types_json)
    type_desc_map = build_type_desc_map(type_defs)
    os.makedirs(output_dir, exist_ok=True)

    grouped = defaultdict(list)
    for func in function_list:
        grouped[func.get("file", "unknown")].append(func)

    items = list(grouped.items())
    for _, _, (file_path, funcs) in iter_progress(items, "Generating docx"):
        # -- local type-ref renumbering --
        if local_table:
            from generators.common import build_local_type_refs
            local_type_refs, local_ref_to_type = build_local_type_refs(funcs, type_refs)
        else:
            local_type_refs = type_refs
            local_ref_to_type = {}

        base = os.path.splitext(os.path.basename(file_path))[0]
        doc = _create_document()

        doc.add_heading(os.path.basename(file_path), level=1)
        doc.add_paragraph(f"Source file: {os.path.basename(file_path)}")
        doc.add_paragraph(f"Functions: {len(funcs)}")

        for raw_func in funcs:
            func = normalize_function_for_doc(raw_func)
            _add_function_section(doc, func, local_type_refs, type_desc_map, figures_dir, heading_level=2,
                                  style=style, sections=sections, out_param_location=out_param_location)
            doc.add_page_break()

        # -- local appendix --
        if local_table and local_ref_to_type:
            from generators.docx.appendix import _add_local_appendix_docx
            _add_local_appendix_docx(doc, type_defs, local_ref_to_type, language)

        safe_base = _sanitize_filename(base)
        doc.save(os.path.join(output_dir, f"{safe_base}.docx"))


def generate_function_docx(function_list, types_json, figures_dir, output_dir="DOCX",
                           group_by="function", style="plain", sections=None,
                           local_table=False, language="c", out_param_location="inputs"):
    functions = function_list

    if group_by == "file":
        generate_function_docx_by_file(functions, types_json, figures_dir, output_dir, style=style,
                                       sections=sections, local_table=local_table, language=language,
                                       out_param_location=out_param_location)
    else:
        generate_function_docx_per_function(functions, types_json, figures_dir, output_dir, style=style,
                                            sections=sections, local_table=local_table, language=language,
                                            out_param_location=out_param_location)
