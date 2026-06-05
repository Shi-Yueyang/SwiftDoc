#!/usr/bin/env python3
"""Demo: rescue a function trapped in a tree-sitter ERROR node.

The #ifdef / #else block injects braces that only balance when one
branch is active.  Tree-sitter sees both branches → ERROR.

Fix: strip #-lines from the ERROR text and re-parse.

Usage:  python examples/c/bug_test/demo_rescue_parse.py
"""

import re
import tree_sitter_c
from tree_sitter import Language, Parser

C_LANG = Language(tree_sitter_c.language())

CASE = """
void guarded_func(int mode) {

#ifdef FEATURE_X
    if (mode > 0) {
#else
    while (mode < 10) {
#endif

        do_work(mode);
    }
}

void func_after(){
    
}
"""


def _name_of(func_node):
    decl = func_node.child_by_field_name("declarator")
    for child in decl.children:
        if child.type == "identifier":
            return child.text.decode()
    return "?"


def collect_functions(root_node):
    stack = [root_node]
    while stack:
        node = stack.pop()
        if node.type == "function_definition":
            yield node
        for child in node.children:
            stack.append(child)


# ── parse ───────────────────────────────────────────────────────────────────

parser = Parser(C_LANG)
tree = parser.parse(bytes(CASE, "utf8"))

funcs = list(collect_functions(tree.root_node))
if funcs:
    print(f"pass 1: found {_name_of(funcs[0])}")
else:
    print("pass 1: nothing — unbalanced braces created an ERROR")

# Find ERROR nodes, strip #-lines, re-parse
for node in tree.root_node.children:
    if node.type == "ERROR":

        print(f"\nERROR text ({node.end_byte - node.start_byte} bytes):")
        print("─" * 40)
        print(node.text.decode())
        print("─" * 40)

        cleaned = re.sub(r"^[ \t]*#.*$", "", node.text.decode(), flags=re.MULTILINE)
        print(f"\ncleaned ({len(cleaned)} bytes):")
        print("─" * 40)
        print(cleaned)
        print("─" * 40)

        tree2 = Parser(C_LANG).parse(bytes(cleaned, "utf8"))
        for fn in collect_functions(tree2.root_node):
            if fn:
                print(f"pass 2: rescued {_name_of(fn)}  ✓")
            else:
                print("pass 2: nothing — unbalanced braces created an ERROR")

