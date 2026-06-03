"""Parser registry for swift-doc.

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

import logging
import os

from parsers.c import CParser
from parsers.ada import AdaParser

logger = logging.getLogger(__name__)

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


def detect_language(project_dir: str) -> str:
    """Auto-detect the source language by scanning file extensions in *project_dir*.

    Returns the language key with the most matching source/header files.
    Falls back to the first registered parser when no files match.
    """
    ext_to_lang: dict[str, str] = {}
    for lang, parser in _PARSERS.items():
        for ext in parser.source_extensions + parser.header_extensions:
            ext_to_lang[ext] = lang

    if not ext_to_lang:
        fallback = next(iter(_PARSERS))
        logger.warning("No parsers define extensions, falling back to '%s'", fallback)
        return fallback

    counts: dict[str, int] = {lang: 0 for lang in _PARSERS}

    if os.path.isfile(project_dir):
        for ext, lang in ext_to_lang.items():
            if project_dir.endswith(ext):
                counts[lang] += 1
    else:
        for _root, _dirs, filenames in os.walk(project_dir):
            for f in filenames:
                for ext, lang in ext_to_lang.items():
                    if f.endswith(ext):
                        counts[lang] += 1
                        break

    candidates = [(c, lang) for lang, c in counts.items() if c > 0]

    if not candidates:
        fallback = next(iter(_PARSERS))
        logger.warning(
            "No files with known extensions in '%s', falling back to '%s'",
            project_dir, fallback,
        )
        return fallback

    candidates.sort(key=lambda x: (-x[0], x[1]))
    detected = candidates[0][1]

    logger.info("Detected language: %s (%d source files)", detected, candidates[0][0])
    if len(candidates) > 1:
        logger.debug(
            "Other candidates: %s",
            ", ".join(f"{l}={c}" for c, l in candidates[1:]),
        )
    return detected
