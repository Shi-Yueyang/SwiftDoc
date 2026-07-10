import os
import re
import logging
from typing import Optional, Set

from docx import Document
from docx.shared import Inches, Pt, Cm
from docx.oxml.ns import qn

from generators.common import generate_definition

logger = logging.getLogger(__name__)

HEADER_SHADING = "D9E2F3"


def _set_cell_shading(cell, color):
    from docx.oxml import OxmlElement
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), color)
    shading.set(qn("w:val"), "clear")
    tcPr.append(shading)


def _set_cell_text(cell, text, bold=False, font_size=9):
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run(str(text) if text is not None else "")
    run.font.size = Pt(font_size)
    run.font.name = "Calibri"
    run.bold = bold


def _set_cell_code(cell, code):
    cell.text = ""
    lines = code.split("\n")
    for i, line in enumerate(lines):
        if i == 0:
            p = cell.paragraphs[0]
        else:
            p = cell.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(line)
        run.font.name = "Consolas"
        run.font.size = Pt(9)


def _set_cell_text_with_eastasian(cell, text, bold=False):
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run(str(text) if text is not None else "")
    run.font.size = Pt(9)
    run.font.name = "Calibri"
    run.element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    run.bold = bold


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

    heading_style = doc.styles["Heading 1"]
    heading_style.font.size = Pt(16)
    heading_style.font.bold = True

    return doc


def generate_appendix_docx(types_data: dict, output_docx_path: str, filter_types: Optional[Set[str]] = None, language: str = "c") -> None:
    data = types_data
    type_defs = data.get("type_definitions", {})
    type_refs = data.get("type_references", {})

    if not type_defs:
        logger.warning("No type definitions found.")
        return

    rows = []
    for type_name, ref in type_refs.items():
        if type_name not in type_defs:
            continue
        if filter_types is not None and type_name not in filter_types:
            continue
        info = type_defs[type_name]
        definition = generate_definition(type_name, info, language=language)
        description = info.get("type_description", "").strip()
        if not description:
            description = "No description"
        rows.append((ref, type_name, definition, description))

    def sort_key(row):
        match = re.search(r"A_(\d+)", row[0])
        if match:
            return int(match.group(1))
        return 0
    rows.sort(key=sort_key)

    doc = _create_document()
    doc.add_heading("Appendix Global Data Structures", level=1)

    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"

    headers = ["Reference REF", "Identifier", "Definition", "Description"]
    for i, header in enumerate(headers):
        _set_cell_text_with_eastasian(table.rows[0].cells[i], header, bold=True)
        _set_cell_shading(table.rows[0].cells[i], HEADER_SHADING)

    for ref, ident, definition, desc in rows:
        row = table.add_row()
        _set_cell_text(row.cells[0], ref)
        _set_cell_text(row.cells[1], ident)
        _set_cell_code(row.cells[2], definition)
        _set_cell_text_with_eastasian(row.cells[3], desc)

    os.makedirs(os.path.dirname(output_docx_path), exist_ok=True)
    doc.save(output_docx_path)
    logger.debug("Appendix saved to %s", output_docx_path)


def _add_embedded_appendix_docx(doc, type_defs, embedded_ref_to_type, language="c"):
    """Append an embedded types appendix table to an existing docx document.

    Parameters
    ----------
    doc : Document
        The docx document to append to.
    type_defs : dict[str, dict]
        Project-wide type definitions.
    embedded_ref_to_type : dict[str, str]
        Mapping from embedded ref code (e.g. "A_1") to type name.
    language : str
        "c" or "ada" -- controls definition syntax.
    """
    doc.add_heading("Appendix - Embedded Type References", level=2)

    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"

    headers = ["Reference REF", "Identifier", "Definition", "Description"]
    for i, header in enumerate(headers):
        _set_cell_text_with_eastasian(table.rows[0].cells[i], header, bold=True)
        _set_cell_shading(table.rows[0].cells[i], HEADER_SHADING)

    def sort_key(code):
        match = re.search(r"A_(\d+)", code)
        if match:
            return int(match.group(1))
        return 0

    for code in sorted(embedded_ref_to_type, key=sort_key):
        tname = embedded_ref_to_type[code]
        info = type_defs.get(tname, {})
        definition = generate_definition(tname, info, language=language)
        description = info.get("type_description", "").strip() or "No description"
        row = table.add_row()
        _set_cell_text(row.cells[0], code)
        _set_cell_text(row.cells[1], tname)
        _set_cell_code(row.cells[2], definition)
        _set_cell_text_with_eastasian(row.cells[3], description)

    doc.add_paragraph()
