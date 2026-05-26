"""
Generator registry for auto-md.

Add new output formats by creating a package (e.g., generators/html/) and registering it here.
A generator package must export:
    generate_functions(function_list, types_json, figures_dir, output_dir) -> None
    generate_appendix(types_json, output_path, filter_types=None) -> None
"""

import importlib

_GENERATORS = {
    "markdown": "generators.markdown",
    "docx": "generators.docx",
}

_FORMAT_EXTENSIONS = {
    "markdown": ".md",
    "docx": ".docx",
}


def get_generator(format="markdown"):
    """Return the generator module for the given output format."""
    format = format.lower()
    if format not in _GENERATORS:
        raise ValueError(f"Unsupported format: {format}. Available: {list(_GENERATORS.keys())}")
    return importlib.import_module(_GENERATORS[format])


def register_generator(format, module_path):
    """Register a new generator module for an output format."""
    _GENERATORS[format.lower()] = module_path


def get_format_extension(format):
    """Return the file extension for a given output format."""
    return _FORMAT_EXTENSIONS.get(format.lower(), f".{format.lower()}")
