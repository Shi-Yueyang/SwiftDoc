import os
import json
import logging
import sys

from parsers import get_parser
from generators import get_generator, get_format_extension
from generators.images import generate_function_graphs
from core.utils import build_cache_name


logger = logging.getLogger(__name__)

EXTRACT_PHASE_START_COLOR = "\033[96m"
EXTRACT_PHASE_DONE_COLOR = "\033[32m"
COLOR_RESET = "\033[0m"


def colorize_extract_phase_message(message, color):
    if not sys.stderr.isatty():
        return message
    return f"{color}{message}{COLOR_RESET}"


def build_analysis_paths(cache_dir, project_root):
    folder_name = build_cache_name(project_root)
    return {
        "globals": os.path.join(cache_dir, f"{folder_name}_global_variables.json"),
        "types": os.path.join(cache_dir, f"{folder_name}_global_types.json"),
        "functions": os.path.join(cache_dir, f"{folder_name}_functions.json"),
    }


def extract_global_variables(root_dir, output_json_path, language="c"):
    parser = get_parser(language)
    global_variables = parser.extract_globals(root_dir)
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump({"globals": global_variables}, f, indent=2, ensure_ascii=False)
    logger.info("Found %s global variables", len(global_variables))
    return output_json_path


def run_extract_phase(args):
    parser = get_parser(args.language)

    logger.info(colorize_extract_phase_message("Scanning begins...", EXTRACT_PHASE_START_COLOR))
    logger.info("Language: %s", args.language)
    os.makedirs(args.cache_dir, exist_ok=True)
    enable_ai = getattr(args, "ai", "on") == "on"

    project_root = os.path.normpath(args.root_dir)
    analysis_paths = build_analysis_paths(args.cache_dir, project_root)


    # --- Globals ---
    global_vars = parser.extract_globals(project_root)
    with open(analysis_paths["globals"], "w", encoding="utf-8") as f:
        json.dump({"globals": global_vars}, f, indent=2, ensure_ascii=False)
    logger.info("Found %s global variables", len(global_vars))

    # --- Types ---
    types_data = parser.extract_types(
        project_root,
        args.cache_dir,
        enable_ai=enable_ai,
    )

    # --- Functions ---
    parser.extract_functions(
        project_root,
        output_json_path=analysis_paths["functions"],
        types_data=types_data,
        global_vars=global_vars,
        enable_ai=enable_ai,
    )

    logger.info(colorize_extract_phase_message("Analysis completed.", EXTRACT_PHASE_DONE_COLOR))


def run_docgen_phase(args):
    output_format = getattr(args, "format", "markdown")
    generator = get_generator(output_format)

    logger.info(colorize_extract_phase_message("Generating docs...", EXTRACT_PHASE_START_COLOR))

    cache_dir = args.cache_dir
    root_dir = args.root_dir
    if hasattr(args, "analyse_dirs"):
        analyse_dirs = args.analyse_dirs
    else:
        analyse_dirs = [getattr(args, "analyse_dir", root_dir)]
    output_folder = args.output_folder

    normalized_project_dir = os.path.normpath(root_dir)
    analysis_paths = build_analysis_paths(cache_dir, normalized_project_dir)
    types_json = analysis_paths["types"]
    functions_json = analysis_paths["functions"]

    if not os.path.exists(types_json):
        logger.warning("Types cache file not found: %s", types_json)
        types_data = {"type_definitions": {}, "type_references": {}}
    else:
        with open(types_json, "r", encoding="utf-8") as f:
            types_data = json.load(f)
    type_refs = types_data.get("type_references", {})

    if not os.path.exists(functions_json):
        logger.warning("Functions cache file not found: %s", functions_json)
        all_functions = []
    else:
        with open(functions_json, "r", encoding="utf-8") as f:
            all_functions = json.load(f).get("functions", [])

    normalized_dirs = [os.path.abspath(d) for d in analyse_dirs]
    selected_funcs = []
    seen = set()
    for func in all_functions:
        func_file = os.path.normpath(func["file"])
        for nd in normalized_dirs:
            if func_file == nd or func_file.startswith(nd + os.sep):
                if func["name"] not in seen:
                    selected_funcs.append(func)
                    seen.add(func["name"])
                break

    if not selected_funcs:
        logger.warning("No functions found under %s", analyse_dirs)
        return

    used_type_names = set()
    for func in selected_funcs:
        for inp in func.get("inputs", []):
            if inp.get("kind") == "Global variable":
                base_type = inp["type"].split(" ")[-1]
                used_type_names.add(base_type)
            param_type = inp.get("type", "")
            for word in param_type.split():
                if word in type_refs:
                    used_type_names.add(word)

    figures_dir = os.path.join(output_folder, "figures")
    generate_function_graphs(function_list=selected_funcs, output_dir=figures_dir)

    generator.generate_functions(
        functions_json=None,
        function_list=selected_funcs,
        types_json=types_json,
        figures_dir=figures_dir,
        output_dir=output_folder,
        group_by=getattr(args, "group_by", "function"),
    )

    appendix_ext = get_format_extension(output_format)
    appendix_output = os.path.join(output_folder, f"appendix{appendix_ext}")
    generator.generate_appendix(types_json, appendix_output, filter_types=None, language=getattr(args, "language", "c"))

    logger.info(colorize_extract_phase_message("It's done.", EXTRACT_PHASE_DONE_COLOR))
