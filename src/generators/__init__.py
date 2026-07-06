"""
Generator registry for swift-doc.

Add new output formats by creating a package (e.g., generators/html/) and registering it here.
A generator package must export:
    generate_functions(function_list, types_json, figures_dir, output_dir, **kwargs) -> None
    Accepted kwargs: group_by, style, sections, local_table, language, out_param_location
    generate_appendix(types_data, output_path, **kwargs) -> None
"""

from generators import docx, markdown

_GENERATORS = {
    "markdown": markdown,
    "docx": docx,
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
    return _GENERATORS[format]


def register_generator(format, module_path):
    """Register a new generator module for an output format."""
    _GENERATORS[format.lower()] = module_path


def get_format_extension(format):
    """Return the file extension for a given output format."""
    return _FORMAT_EXTENSIONS.get(format.lower(), f".{format.lower()}")
