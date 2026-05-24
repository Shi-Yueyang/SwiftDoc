"""
Parser registry for auto-md.

Add new languages by creating a package (e.g., parsers/rust/) and registering it here.
A parser package must export three functions:
    extract_globals(project_dir) -> list[dict]
    extract_types(project_dir, cache_dir, enable_ai) -> str
    extract_functions(project_dir, types_json, globals_json, output_json, enable_ai) -> str
"""

import importlib

_PARSERS = {
    "c": "parsers.c",
}


def get_parser(language="c"):
    """Return the parser module for the given language."""
    language = language.lower()
    if language not in _PARSERS:
        raise ValueError(f"Unsupported language: {language}. Available: {list(_PARSERS.keys())}")
    return importlib.import_module(_PARSERS[language])


def register_parser(language, module_path):
    """Register a new parser module for a language."""
    _PARSERS[language.lower()] = module_path
