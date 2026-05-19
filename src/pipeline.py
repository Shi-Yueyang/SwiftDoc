import os
import json
import logging
import sys

from extract_globals import extract_all_globals
from extract_types import refresh_type_definitions
from image_generator import generate_function_graphs
from md_generator import generate_function_md
from appendix_generate import generate_appendix_md
from module_analysis import (
    refresh_functions
)


logger = logging.getLogger(__name__)

EXTRACT_PHASE_START_COLOR = "\033[96m"
EXTRACT_PHASE_DONE_COLOR = "\033[32m"
COLOR_RESET = "\033[0m"


def colorize_extract_phase_message(message, color):
    if not sys.stderr.isatty():
        return message
    return f"{color}{message}{COLOR_RESET}"


def build_analysis_paths(cache_dir, project_root):
    folder_name = os.path.basename(os.path.normpath(project_root))
    return {
        "globals": os.path.join(cache_dir, f"{folder_name}_global_variables.json"),
        "types": os.path.join(cache_dir, f"{folder_name}_global_types.json"),
        "functions": os.path.join(cache_dir, f"{folder_name}_functions.json"),
    }


def extract_global_variables(root_dir, output_json_path):
    # no ai involved, full run each time
    global_variables = extract_all_globals(root_dir)
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump({"globals": global_variables}, f, indent=2, ensure_ascii=False)
    logger.info("Found %s global variables", len(global_variables))
    return output_json_path


def run_extract_phase(args):
    logger.info(colorize_extract_phase_message("Scanning begins...", EXTRACT_PHASE_START_COLOR))
    os.makedirs(args.cache_dir, exist_ok=True)
    enable_ai = getattr(args, "ai", "on") == "on"

    project_root = os.path.normpath(args.root_dir)
    analysis_paths = build_analysis_paths(args.cache_dir, project_root)

    global_vars_json_file = extract_global_variables(project_root, analysis_paths["globals"])
    global_types_json_file = refresh_type_definitions(
        project_root,
        args.cache_dir,
        enable_ai=enable_ai,
    )
    refresh_functions(
        project_dir=project_root,
        types_json_path=global_types_json_file,
        globals_json_path=global_vars_json_file,
        output_json_path=analysis_paths["functions"],
        enable_ai=enable_ai,
    )

    logger.info(colorize_extract_phase_message("Analysis completed.", EXTRACT_PHASE_DONE_COLOR))


def run_docgen_phase(args):
    logger.info(colorize_extract_phase_message("Generating docs...", EXTRACT_PHASE_START_COLOR))
    
    cache_dir = args.cache_dir
    root_dir = args.root_dir
    analyse_dir = args.analyse_dir
    output_folder = args.output_folder

    normalized_project_dir = os.path.normpath(root_dir)
    analysis_paths = build_analysis_paths(cache_dir, normalized_project_dir)
    types_json = analysis_paths["types"]
    functions_json = analysis_paths["functions"]

 
    with open(types_json, 'r', encoding='utf-8') as f:
        types_data = json.load(f)
        type_refs = types_data.get("type_references", {})

    with open(functions_json, 'r', encoding='utf-8') as f:
        all_functions = json.load(f).get("functions", [])


    # filter functions based on analyse_dir
    normalized_analysis_dir = os.path.normpath(analyse_dir)
    selected_funcs = []
    for func in all_functions:
        func_file = os.path.normpath(func["file"])
        if func_file.startswith(normalized_analysis_dir):
            selected_funcs.append(func)

    if not selected_funcs:
        logger.warning("No functions found under %s", analyse_dir)
        return


    # do painting
    used_type_names = set()
    for func in selected_funcs:
        for inp in func.get("inputs", []):
            if inp.get("kind") == "Global variable":
                base_type = inp["type"].split(' ')[-1]
                used_type_names.add(base_type)
            param_type = inp.get("type", "")
            for word in param_type.split():
                if word in type_refs:
                    used_type_names.add(word)

    figures_dir = os.path.join(output_folder, "figures")
    generate_function_graphs(function_list=selected_funcs, output_dir=figures_dir)
    
    generate_function_md(
        functions_json=None,
        function_list=selected_funcs,
        types_json=types_json,
        figures_dir=figures_dir,
        output_dir=output_folder
    )

    appendix_output = os.path.join(output_folder, "appendix.md")
    generate_appendix_md(types_json, appendix_output, filter_types=None)

    logger.info(colorize_extract_phase_message("It's done.", EXTRACT_PHASE_DONE_COLOR))

