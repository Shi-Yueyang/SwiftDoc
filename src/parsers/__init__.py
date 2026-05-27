"""Parser registry for auto-md.

Add new languages by subclassing parsers.base.BaseParser and registering here.
Each parser instance provides:
    language: str
    source_extensions: tuple
    header_extensions: tuple
    supports_types: bool
    supports_globals: bool
    extract_globals(project_dir) -> list[dict]
    extract_types(project_dir, cache_dir, enable_ai) -> dict
    extract_functions(project_dir, output_json_path, types_data, global_vars, enable_ai) -> list[dict]
"""

from parsers.c import CParser
from parsers.ada import AdaParser

_PARSERS = {
    "c": CParser(),
    "ada": AdaParser(),
}


def get_parser(language="c"):
    """Return a parser instance for the given language."""
    language = language.lower()
    if language not in _PARSERS:
        raise ValueError(f"Unsupported language: {language}. Available: {list(_PARSERS.keys())}")
    return _PARSERS[language]


def register_parser(language, parser_instance):
    """Register a parser instance for a language."""
    _PARSERS[language.lower()] = parser_instance
