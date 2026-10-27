"""Parser package for swift-doc.

swift-doc parses C only. The entry point is :class:`CParser`, which
provides:
    extract_globals(project_dir) -> list[dict]
    extract_types(project_dir, cache_dir, enable_ai) -> dict
    extract_functions(project_dir, output_json_path, types_data, global_vars, enable_ai) -> list[dict]
"""

from parsers.c import CParser

__all__ = ["CParser"]
