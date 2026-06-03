"""Abstract base class for language parsers.

To add a new language, subclass BaseParser, implement extract_functions(),
and optionally override extract_globals() / extract_types().
Register with parsers.register_parser().
"""

from abc import ABC, abstractmethod

from parsers.types import GlobalVar, TypesData, FuncDef


class BaseParser(ABC):
    language: str = ""
    source_extensions: tuple[str, ...] = ()
    header_extensions: tuple[str, ...] = ()
    supports_types: bool = True
    supports_globals: bool = True

    @abstractmethod
    def extract_functions(
        self,
        project_dir: str,
        output_json_path: str,
        types_data: TypesData,
        global_vars: list[GlobalVar],
        enable_ai: bool = True,
        ignore_calls: set | None = None,
    ) -> list[FuncDef]:
        """Parse source files, refresh cache, and return function dicts."""
        ...

    def extract_globals(self, project_dir: str) -> list[GlobalVar]:
        """Return global variable dicts found under *project_dir*."""
        return []

    def extract_types(
        self, project_dir: str, cache_dir: str, enable_ai: bool = True,
        ignore_types: set | None = None,
    ) -> TypesData:
        """Extract, refresh, persist, and return type metadata for *project_dir*."""
        return {"description": "", "type_definitions": {}, "type_references": {}}
