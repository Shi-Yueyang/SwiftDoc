"""Shared tree-sitter helpers for the Ada parser."""


def find_ada_identifier(node):
    """Find the first named identifier child of a tree-sitter node."""
    for child in node.children:
        if child.is_named and child.type == "identifier":
            return child
    return None
