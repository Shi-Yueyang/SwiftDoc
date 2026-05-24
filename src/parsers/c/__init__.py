from parsers.base import BaseParser
from parsers.c.globals import extract_all_globals as _extract_globals
from parsers.c.types import refresh_type_definitions as _extract_types
from parsers.c.functions import refresh_functions as _extract_functions


class CParser(BaseParser):
    language = "c"
    source_extensions = (".c",)
    header_extensions = (".h",)
    supports_types = True
    supports_globals = True

    def extract_globals(self, project_dir):
        return _extract_globals(project_dir)

    def extract_types(self, project_dir, cache_dir, enable_ai=True):
        return _extract_types(project_dir, cache_dir, enable_ai=enable_ai)

    def extract_functions(self, project_dir, types_json_path, globals_json_path,
                          output_json_path, enable_ai=True):
        return _extract_functions(
            project_dir,
            types_json_path=types_json_path,
            globals_json_path=globals_json_path,
            output_json_path=output_json_path,
            enable_ai=enable_ai,
        )
