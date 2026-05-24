"""Abstract base class for language parsers.

To add a new language, subclass BaseParser, implement extract_functions(),
and optionally override extract_globals() / extract_types().
Register with parsers.register_parser().
"""

from abc import ABC, abstractmethod


class BaseParser(ABC):
    language: str = ""
    source_extensions: tuple = ()
    header_extensions: tuple = ()
    supports_types: bool = True
    supports_globals: bool = True

    @abstractmethod
    def extract_functions(self, project_dir, types_json_path, globals_json_path,
                          output_json_path, enable_ai=True):
        """Parse source files under project_dir and write function data to output_json_path.

        Returns the path to the written functions JSON file.
        """
        ...

    def extract_globals(self, project_dir):
        """Return a list of global variable dicts found under project_dir.

        Override if the language has global/static variable declarations.
        Default returns an empty list.
        """
        return []

    def extract_types(self, project_dir, cache_dir, enable_ai=True):
        """Extract type definitions, diff against cache, enrich with AI, and write back.

        Returns the path to the types cache JSON file.
        Override if the language has type definitions separate from function bodies.
        Default returns an empty string (no types file).
        """
        return ""
