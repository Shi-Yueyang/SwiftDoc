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
import logging
import chardet
import tree_sitter_c
from tree_sitter import Language, Parser
from core.utils import get_node_text, find_identifier, highlight_message, collect_source_files, filter_source_files_by_analyse_dirs
from parsers.common import (
    load_previous_function_cache,
    write_function_cache,
    prepare_function_metadata,
    enrich_function_with_ai,
    summarize_ai_result,
    is_missing_algorithm_logic,
    refresh_functions,
)

logger = logging.getLogger(__name__)

C_LANGUAGE = Language(tree_sitter_c.language())
parser = Parser(C_LANGUAGE)

# Standard library functions to exclude from call graphs
_IGNORED_CALLS = {"memcpy", "memset"}


def _collect_file_defines(lines: list[str]) -> set:
    """Gather macro names ``#define``d anywhere in the file.

    The preprocessor cannot see included headers, so file-local
    ``#define NAME`` / ``#define NAME(...)`` count as defined.
    """
    names: set = set()
    for line in lines:
        m = re.match(r"^\s*#\s*define\s+([A-Za-z_]\w*)", line)
        if m:
            names.add(m.group(1))
    return names


def _eval_if_expr(expr: str, known: set, lineno: int) -> bool | None:
    """Evaluate a ``#if`` / ``#elif`` condition.

    Returns True/False, or None when the expression cannot be resolved.
    ``defined(NAME)`` and ``defined NAME`` use *known*; remaining
    identifiers become 0 (per the C preprocessor, undefined names are
    0 in constant expressions).
    """
    resolved = re.sub(
        r"defined\s*\(\s*([A-Za-z_]\w*)\s*\)",
        lambda mo: "1" if mo.group(1) in known else "0",
        expr,
    )
    resolved = re.sub(
        r"defined\s+([A-Za-z_]\w*)",
        lambda mo: "1" if mo.group(1) in known else "0",
        resolved,
    )
    # Any other identifier: known macro → 1 (truthy), unknown → 0
    resolved = re.sub(
        r"[A-Za-z_]\w*",
        lambda mo: "1" if mo.group(0) in known else "0",
        resolved,
    )
    try:
        return bool(eval(resolved, {"__builtins__": {}}))
    except Exception:
        logger.debug(
            "Cannot evaluate #if expression %r at line %d", expr, lineno,
        )
        return None


def preprocess_c_code(code: str, defines: set | None = None) -> str:
    """Resolve ``#if`` / ``#ifdef`` / ``#ifndef`` / ``#elif`` / ``#else``.

    Each nesting level tracks whether a branch of its ``#if`` chain has
    already been taken, so exactly one branch survives — never two
    (variant ``return`` statements leaking into function analysis) and
    never zero.  ``#ifdef``/``#ifndef`` test the macro against *defines*
    plus names ``#define``d in the file itself.  ``#if`` expressions are
    evaluated via ``defined()`` resolution with unknown identifiers → 0
    (C semantics); ``#if 0`` is therefore always dropped.  An expression
    that still cannot be resolved conservatively keeps its first branch
    and marks the chain as taken.  Directive lines are stripped; other
    lines (including ``#define``) are emitted only while every open
    level is active.
    """
    if defines is None:
        defines = set()

    lines = code.split("\n")
    known = set(defines) | _collect_file_defines(lines)

    result = []
    # Each stack entry: [active, taken] — is the current branch selected,
    # and has any branch of this level's #if chain been selected?
    stack: list[list[bool]] = []

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()

        # --- #ifdef MACRO ---
        m = re.match(r"^#\s*ifdef\s+(\w+)", stripped)
        if m:
            active = m.group(1) in known
            stack.append([active, active])
            continue

        # --- #ifndef MACRO ---
        m = re.match(r"^#\s*ifndef\s+(\w+)", stripped)
        if m:
            active = m.group(1) not in known
            stack.append([active, active])
            continue

        # --- #if EXPR ---
        m = re.match(r"^#\s*if\s+(.+)", stripped)
        if m:
            value = _eval_if_expr(m.group(1), known, lineno)
            # Unresolvable: conservatively keep the first branch
            active = True if value is None else value
            stack.append([active, active])
            continue

        # --- #elif EXPR ---
        m = re.match(r"^#\s*elif\s+(.+)", stripped)
        if m:
            if stack:
                entry = stack[-1]
                if entry[1]:  # an earlier branch already won
                    entry[0] = False
                else:
                    value = _eval_if_expr(m.group(1), known, lineno)
                    active = True if value is None else value
                    entry[0] = active
                    entry[1] = entry[1] or active
            continue

        # --- #else ---
        if re.match(r"^#\s*else\b", stripped):
            if stack:
                entry = stack[-1]
                if not entry[1]:  # no branch taken yet → #else wins
                    entry[0] = True
                    entry[1] = True
                else:
                    entry[0] = False
            continue

        # --- #endif ---
        if re.match(r"^#\s*endif\b", stripped):
            if stack:
                stack.pop()
            continue

        # --- Emit or skip ---
        if all(active for active, _taken in stack):
            result.append(line)

    return "\n".join(result)


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
            # Build full type: type_node gives the base type (int, char, etc.),
            # but pointer stars live in pointer_declarator children.
            type_parts = []
            for child in param.children:
                if child.type in ("pointer_declarator", "array_declarator",
                                  "function_declarator"):
                    continue  # declarators wrap the name, handled below
                if child == param_name_node:
                    continue
                if child.type == "identifier" and child != param_name_node:
                    continue
                type_parts.append(get_node_text(child).strip())
            # Fallback: extract everything before the identifier from full text
            if not type_parts:
                full_text = get_node_text(param)
                param_type = full_text.replace(param_name, "").strip()
                param_type = param_type.rstrip(",").strip()
            else:
                param_type = " ".join(type_parts).strip()
            # Also check the declarator for pointer stars
            for child in param.children:
                if child.type in ("pointer_declarator",):
                    for sub in child.children:
                        if sub.type == "*":
                            param_type += "*"
            params.append({"name": param_name, "type": param_type})
    return params


# 提取return语句
def find_return_statements(func_body_node):
    """Collect distinct return expressions, in source order.

    Bare ``return;`` yields nothing; repeated expressions (guard-clause
    style ``return ret;``) collapse to a single entry.  The expression
    is taken from the statement's named child, so identifiers merely
    *containing* "return" (``g_return_val``) survive intact.
    """
    returns = []
    if func_body_node is None:
        return returns
    collected = []
    stack = [func_body_node]
    while stack:
        node = stack.pop()
        if node.type == "return_statement":
            expr = ""
            for child in node.children:
                if child.is_named:
                    expr = get_node_text(child).strip()
                    break
            if expr:
                collected.append((node.start_byte, expr))
        else:
            for child in node.children:
                stack.append(child)
    collected.sort(key=lambda item: item[0])
    for _byte, expr in collected:
        if expr not in returns:
            returns.append(expr)
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
    """Check if an identifier is being written to.

    Walks up through subscript (arr[0]), field (s->x), and pointer (*p)
    access chains to find the enclosing assignment or update expression.
    """
    # Walk up through access chains to find the actual expression root
    expr = node
    _ACCESS_TYPES = ("subscript_expression", "field_expression", "pointer_expression")
    while expr.parent is not None and expr.parent.type in _ACCESS_TYPES:
        expr = expr.parent

    parent = expr.parent
    if parent is None:
        return False
    if parent.type == "assignment_expression":
        left = parent.child_by_field_name("left")
        if left is not None and left.start_byte == expr.start_byte:
            return True
    if parent.type == "update_expression":
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
                # (TypeName)(expr) is a C cast, not a function call.
                # Tree-sitter parses these as call_expression nodes where the
                # "function" is a parenthesized_expression wrapping a bare identifier.
                if _is_cast_expression(func_node):
                    pass  # skip — it's a cast
                else:
                    ident = find_identifier(func_node)
                    if ident:
                        called.add(get_node_text(ident))
        for child in node.children:
            stack.append(child)
    return list(called)


def _is_cast_expression(func_node):
    """Return True if *func_node* is a parenthesized type name (a C cast)."""
    if func_node.type != "parenthesized_expression":
        return False
    # Find the first named child inside the parens
    named = [c for c in func_node.children if c.is_named]
    return len(named) == 1 and named[0].type == "identifier"


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


def _analyze_pointer_directions(body_node, pointer_param_names):
    """Determine direction (in/out/in out) for pointer parameters by analyzing body usage.

    Walks the function body looking for pointer_expression nodes (*param).
    If the dereferenced pointer is only read → "in",
    only written (LHS of =, +=, -=, etc.) → "out",
    both read and written (separate contexts, or ++/--) → "in out".
    """
    usage = {p: {"read": False, "write": False} for p in pointer_param_names}
    if body_node is None:
        return {p: "in" for p in pointer_param_names}

    stack = [body_node]
    while stack:
        node = stack.pop()
        if node.type == "pointer_expression":
            ident = find_identifier(node)
            if ident:
                name = get_node_text(ident)
                if name in pointer_param_names:
                    parent = node.parent
                    if parent is not None and parent.type == "assignment_expression":
                        # tree-sitter node identity is not reliable; compare byte positions.
                        # assignment_expression children: [left, operator, right]
                        is_left = (parent.children and
                                   parent.children[0].start_byte == node.start_byte)
                        if is_left:
                            usage[name]["write"] = True
                            # Compound assignments (+=, -=, ...) count as write-only
                            # for parameter direction purposes.
                        else:
                            usage[name]["read"] = True
                    elif parent is not None and parent.type == "update_expression":
                        # ++/--: both read and write the pointed-to value
                        usage[name]["read"] = True
                        usage[name]["write"] = True
                    else:
                        usage[name]["read"] = True
        for child in node.children:
            stack.append(child)

    result = {}
    for name, acc in usage.items():
        if acc["read"] and acc["write"]:
            result[name] = "in out"
        elif acc["write"]:
            result[name] = "out"
        else:
            result[name] = "in"
    return result


def _extract_return_type(func_node):
    """Extract the full return type from a function_definition node, including pointer stars."""
    type_node = func_node.child_by_field_name("type")
    return_type = get_node_text(type_node).strip() if type_node else "unknown"

    declarator = func_node.child_by_field_name("declarator")
    if declarator:
        node = declarator
        while node is not None and node.type == "pointer_declarator":
            return_type += "*"
            # Advance to the nested declarator
            next_node = None
            for child in node.children:
                if child.type in ("function_declarator", "pointer_declarator",
                                  "array_declarator", "identifier"):
                    next_node = child
                    break
            node = next_node
    return return_type


def extract_functions_from_c_file(c_file_path, type_refs, global_lookup, defines=None):
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
    raw_code = code  # keep raw source before preprocessing

    # ── preprocess: resolve #ifdef / #ifndef based on --define flags ──
    code = preprocess_c_code(code, defines)

    tree = parser.parse(bytes(code, "utf8"))
    root_node = tree.root_node

    functions = []
    # Walk recursively: functions inside #ifdef / #if / #else are nested
    # under preproc_* nodes, not direct children of translation_unit.
    outer_stack = [root_node]
    while outer_stack:
        node = outer_stack.pop()
        if node.type == "function_definition":
            result = _extract_one_function(node, c_file_path, type_refs, global_lookup)
            if result:
                functions.extend(result)
        else:
            for child in node.children:
                outer_stack.append(child)

    # ── warn about remaining ERROR nodes ──────────────────────────────
    error_nodes = [n for n in root_node.children if n.type == "ERROR"]
    if error_nodes:
        lines = [
            "%s: %d parse error(s) after preprocessing:" % (c_file_path, len(error_nodes))
        ]
        for i, en in enumerate(error_nodes, 1):
            lineno = en.start_point[0] + 1  # tree-sitter row is 0-based
            text = en.text.decode(errors="replace")
            top_lines = text.split("\n")[:3]
            snippet = "\n    ".join(
                ln.strip()[:80] for ln in top_lines if ln.strip()
            )
            if not snippet:
                snippet = "(empty)"
            lines.append("  error %d (line %d):" % (i, lineno))
            lines.append("    %s" % snippet)
        lines.append("  hint: try --define to activate guarded preprocessor regions")
        logger.warning("\n".join(lines))

    # ── augment with raw-source line numbers and conditional macros ─────
    _augment_functions_from_raw_source(raw_code, functions)

    return functions


def _extract_one_function(func_node, c_file_path, type_refs, global_lookup):
    """Extract a single function_definition node into a function dict.

    Used by both the normal walk and the rescue pass.
    """
    declarator_node = func_node.child_by_field_name("declarator")
    if declarator_node is None:
        return None
    func_name_node = find_identifier(declarator_node)
    if func_name_node is None:
        return None
    function_name = get_node_text(func_name_node)

    body_node = func_node.child_by_field_name("body")
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
    pointer_params = set()
    for p in params:
        inputs.append({
            "name": p["name"], "kind": "parameter",
            "direction": "in", "type": p["type"],
            "type_ref": get_type_ref(p["type"], type_refs) or "",
        })

        if "*" in p["type"]:
            pointer_params.add(p["name"])

    pointer_directions = _analyze_pointer_directions(body_node, pointer_params)
    for inp in inputs:
        if inp["name"] in pointer_directions:
            inp["direction"] = pointer_directions[inp["name"]]

    if body_node:
        global_written = set()
        global_read = set()
        referenced_globals = {}
        global_stack = [body_node]
        while global_stack:
            gnode = global_stack.pop()
            if gnode.type == "identifier":
                name = get_node_text(gnode)
                global_info = resolve_global_info(global_lookup, c_file_path, name)
                if global_info is not None:
                    referenced_globals[name] = global_info
                    if is_identifier_written(gnode):
                        global_written.add(name)
                    else:
                        global_read.add(name)
            else:
                for sub in gnode.children:
                    global_stack.append(sub)

        for gname in global_read | global_written:
            ginfo = referenced_globals[gname]
            gtype = ginfo["type"]
            direction = "in out" if gname in global_written else "in"
            type_ref = get_type_ref(gtype, type_refs)
            if type_ref is None:
                type_ref = ""

            inputs.append({
                "name": gname, "kind": "Global variable",
                "direction": direction, "type": gtype, "type_ref": type_ref,
            })

    return_type = _extract_return_type(func_node)
    return_exprs = find_return_statements(body_node)
    calls = extract_calls_from_body(body_node)
    calls = [c for c in calls if c not in _IGNORED_CALLS]

    start_line = func_node.start_point[0] + 1

    return [{
        "name": function_name, "file": c_file_path,
        "start_line": start_line,
        "return_type": return_type, "inputs": inputs,
        "returns": return_exprs, "body_code": body_code,
        "normalized_body": normalized_body, "calls": calls,
    }]


def _macros_from_directive(stripped: str) -> set[str]:
    """Extract the feature-flag macro names referenced by a single
    preprocessor conditional line (``#ifdef`` / ``#ifndef`` / ``#if defined()``
    / ``#elif defined()``).

    Only names in ``defined(...)`` and ``#if(n)def`` guards are captured —
    bare identifiers in ``#if MACRO`` expressions are intentionally excluded
    (they could be numeric constants).
    """
    macros: set[str] = set()

    # #ifdef MACRO / #ifndef MACRO
    m = re.match(r"#ifn?def\s+(\w+)", stripped)
    if m:
        macros.add(m.group(1))
        return macros

    # #if defined(MACRO) …  /  #elif defined(MACRO) …
    m = re.match(r"#(?:if|elif)\s+(.+)", stripped)
    if m:
        for dm in re.finditer(r"defined\s*\(\s*(\w+)\s*\)", m.group(1)):
            macros.add(dm.group(1))

    return macros


def _scan_conditional_macros(raw_code: str) -> dict[int, set[str]]:
    """Scan raw C code for conditional compilation macros referenced in
    ``#ifdef`` / ``#ifndef`` / ``#if defined()`` / ``#elif defined()``.

    Returns a ``{line_number: set(macro_names)}`` dict.
    """
    macros_by_line: dict[int, set[str]] = {}
    for i, line in enumerate(raw_code.split("\n"), 1):
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        macros = _macros_from_directive(stripped)
        if macros:
            macros_by_line.setdefault(i, set()).update(macros)
    return macros_by_line


def _scan_conditional_regions(
    raw_code: str,
) -> list[tuple[int, int, set[str]]]:
    """Scan raw C code for conditional-compilation *blocks*.

    Each ``#ifdef`` / ``#ifndef`` / ``#if defined()`` … ``#endif`` region is
    returned as ``(open_line, close_line, macros)``, where *macros* are all
    the names that gate the block (including those on ``#else`` / ``#elif``
    branches, which stay inside the same region).  These describe the *span*
    a guard encloses, so a directive that wraps a whole file (its ``#ifdef``
    line sits above every function) can still be attributed to the functions
    it actually guards.  Blocks with no captured macro name are skipped.
    """
    lines = raw_code.split("\n")
    regions: list[tuple[int, int, set[str]]] = []
    stack: list[tuple[int, set[str]]] = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        if re.match(r"#if(def|ndef)?\b", stripped):
            stack.append((i, _macros_from_directive(stripped)))
            continue

        if re.match(r"#endif\b", stripped):
            if stack:
                open_line, macros = stack.pop()
                if macros:
                    regions.append((open_line, i, macros))
            continue

        # #else / #elif stay inside the enclosing region but may add names.
        if re.match(r"#(?:else|elif)\b", stripped) and stack:
            stack[-1][1].update(_macros_from_directive(stripped))

    # Unterminated guards extend to end-of-file.
    eof = len(lines)
    for open_line, macros in stack:
        if macros:
            regions.append((open_line, eof, macros))

    # Outermost guards first (earliest #if, widest span) so a file-level
    # guard precedes any inner conditional that also encloses a function.
    regions.sort(key=lambda r: (r[0], -r[1]))
    return regions


def _find_function_start_line(raw_code: str, func_name: str) -> int | None:
    """Locate the raw-source line where *func_name* is defined.

    Searches for ``type … func_name(`` patterns, skipping preprocessor
    directives.  Returns a 1-based line number or *None* when the name
    cannot be reliably found in definition context.
    """
    lines = raw_code.split("\n")
    pattern = re.compile(r"\b" + re.escape(func_name) + r"\s*\(")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        m = pattern.search(stripped)
        if m:
            before = stripped[:m.start()].strip()
            # Must have a type/qualifier before the name — filter out
            # calls (bare name) and statement starts.
            if before and before[0] not in ";,=().{}[]":
                return i
    return None


def _augment_functions_from_raw_source(
    raw_code: str, functions: list[dict]
) -> list[dict]:
    """Augment each function dict with raw-source ``start_line`` and
    ``conditional_macros`` by correlating macro directives to function
    line ranges.

    A macro is attributed to a function when either (a) its directive line
    falls inside the function's own line range, or (b) it guards a region
    that *encloses* the function — a file-wide ``#ifdef … #endif`` whose
    opening directive sits above every function definition.
    """
    if not functions:
        return functions

    line_macros = _scan_conditional_macros(raw_code)
    regions = _scan_conditional_regions(raw_code)

    # Find raw start_line for every function
    for func in functions:
        raw_start = _find_function_start_line(raw_code, func["name"])
        if raw_start is not None:
            func["start_line"] = raw_start

    # Sort by start_line so we can compute per-function line ranges
    sorted_funcs = sorted(functions, key=lambda f: f.get("start_line", 0))
    all_macro_lines = sorted(line_macros.keys())
    raw_line_count = len(raw_code.split("\n"))

    for idx, func in enumerate(sorted_funcs):
        start = func.get("start_line", 0)
        if idx + 1 < len(sorted_funcs):
            end = sorted_funcs[idx + 1].get("start_line", raw_line_count) - 1
        else:
            end = raw_line_count

        macros: list[str] = []
        seen: set[str] = set()

        # (b) Enclosing guards: regions whose span contains this function.
        for open_line, close_line, guard_macros in regions:
            if open_line <= start <= close_line:
                for macro in sorted(guard_macros):
                    if macro not in seen:
                        macros.append(macro)
                        seen.add(macro)

        # (a) Local conditionals inside the function's own line range.
        for ml in all_macro_lines:
            if start <= ml <= end:
                for macro in sorted(line_macros[ml]):
                    if macro not in seen:
                        macros.append(macro)
                        seen.add(macro)

        func["conditional_macros"] = macros

    return functions


def scan_all_functions(project_dir, types_data, global_vars, analyse_dirs=None, defines=None):
    """Scan .c files and return a list of function dicts (no cache I/O)."""
    c_files = collect_source_files(project_dir, (".c",))
    if analyse_dirs is not None:
        c_files = filter_source_files_by_analyse_dirs(c_files, analyse_dirs)
        logger.info("Filtered to %s .c file(s) under analyse_dirs", len(c_files))
    if not c_files:
        logger.debug("No .c files found in %s", project_dir)
        return []

    type_refs = types_data.get("type_references", {})
    global_lookup = build_global_lookup(global_vars)
    all_functions = []
    for cf in c_files:
        funcs = extract_functions_from_c_file(cf, type_refs, global_lookup, defines=defines)
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