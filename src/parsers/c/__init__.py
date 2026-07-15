from parsers.base import BaseParser
from parsers.types import GlobalVar, TypesData, FuncDef
from parsers.c.globals import extract_all_globals
from parsers.c.types import scan_project_types, refresh_type_definitions
from parsers.c.functions import scan_all_functions, refresh_functions


class CParser(BaseParser):
    language = "c"
    source_extensions = (".c",)
    header_extensions = (".h",)
    supports_types = True
    supports_globals = True

    def extract_globals(self, project_dir: str, analyse_dirs: list[str] | None = None) -> list[GlobalVar]:
        return extract_all_globals(project_dir, analyse_dirs=analyse_dirs)

    def extract_types(
        self, project_dir: str, cache_dir: str, enable_ai: bool = True,
        ai_workers: int = 6,
    ) -> TypesData:
        fresh_types = scan_project_types(project_dir)
        return refresh_type_definitions(
            fresh_types, project_dir, cache_dir, enable_ai=enable_ai,
            language=self.language, ai_workers=ai_workers,
        )

    def extract_functions(
        self,
        project_dir: str,
        output_json_path: str,
        types_data: TypesData,
        global_vars: list[GlobalVar],
        enable_ai: bool = True,
        analyse_dirs: list[str] | None = None,
        defines: set | None = None,
        ai_workers: int = 6,
    ) -> list[FuncDef]:
        all_functions = scan_all_functions(project_dir, types_data, global_vars, analyse_dirs=analyse_dirs, defines=defines)
        refresh_functions(
            all_functions=all_functions,
            output_json_path=output_json_path,
            types_data=types_data,
            enable_ai=enable_ai,
            language=self.language,
            ai_workers=ai_workers,
        )
        return all_functions
