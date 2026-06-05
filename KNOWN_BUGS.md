# Known Bugs Fixed & Patterns to Watch

Historical bugs that have been fixed in this codebase, and the patterns to avoid repeating them.

1. **Functions inside `#ifdef`/`#if`**: Must walk tree recursively — `root_node.children` skips preproc-wrapped nodes. Use `while stack:` traversal.
2. **tree-sitter node identity**: `node is other` and `node == other` are unreliable. Compare `start_byte` positions instead.
3. **Subscript writes** (`arr[0] = x`): `is_identifier_written()` must walk up through `subscript_expression`, `field_expression`, `pointer_expression` chain to find the enclosing `assignment_expression`.
4. **Cast vs call**: `(TypeName)(expr)` is parsed as `call_expression`. `_is_cast_expression()` detects when the "function" is a `parenthesized_expression` wrapping a bare `identifier` — skip it.
5. **Pointer types**: `child_by_field_name("type")` only returns the base type. Pointer stars live in `pointer_declarator` children — must collect them separately.
6. **Global variable direction**: Two values: `in` (read-only) or `in out` (written at all). No `out`-only for globals.
7. **Pointer parameter direction**: Three-way: `in` (read-only), `out` (write-only), `in out` (both read and written).
8. **Preprocessor-broken functions**: ``#ifdef`` blocks with unbalanced braces can produce ERROR nodes in tree-sitter. The approach is **preprocessing** — use ``--define MACRO`` (or ``[define] macros`` in TOML) to tell the tool which macros are active so it can resolve ``#ifdef`` / ``#ifndef`` before parsing. Any remaining ERROR nodes after preprocessing are logged as warnings. No silent rescue attempts — the user is told exactly what's wrong.
