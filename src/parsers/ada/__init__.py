from parsers.base import BaseParser
from parsers.types import GlobalVar, TypesData, FuncDef
from parsers.ada.globals import extract_all_globals
from parsers.ada.types import scan_project_types, refresh_type_definitions
from parsers.ada.functions import scan_all_functions, refresh_functions


class AdaParser(BaseParser):
    language = "ada"
    source_extensions = (".adb",)
    header_extensions = (".ads",)
    supports_types = True
    supports_globals = True

    def extract_globals(self, project_dir: str) -> list[GlobalVar]:
        return extract_all_globals(project_dir)

    def extract_types(
        self, project_dir: str, cache_dir: str, enable_ai: bool = True,
    ) -> TypesData:
        fresh_types = scan_project_types(project_dir)
        return refresh_type_definitions(
            fresh_types, project_dir, cache_dir, enable_ai=enable_ai, language=self.language,
        )

    def extract_functions(
        self,
        project_dir: str,
        output_json_path: str,
        types_data: TypesData,
        global_vars: list[GlobalVar],
        enable_ai: bool = True,
    ) -> list[FuncDef]:
        all_functions = scan_all_functions(project_dir, types_data, global_vars)
        refresh_functions(
            all_functions=all_functions,
            output_json_path=output_json_path,
            types_data=types_data,
            enable_ai=enable_ai,
            language=self.language,
        )
        return all_functions
