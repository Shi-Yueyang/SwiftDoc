import os
import json
import logging
import shutil
import sys

from parsers import get_parser
from generators import get_generator, get_format_extension
from generators.images import generate_function_graphs
from core.utils import build_cache_name
from _version import VERSION


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

    # -- cache versioning: wipe stale cache when VERSION has changed --
    version_file = os.path.join(args.cache_dir, ".cache_version")
    if os.path.isdir(args.cache_dir):
        try:
            with open(version_file, "r") as _f:
                cached_version = _f.read().strip()
        except (FileNotFoundError, OSError):
            cached_version = None
        if cached_version and cached_version != VERSION:
            logger.info("Version changed (%s → %s), clearing cache", cached_version, VERSION)
            shutil.rmtree(args.cache_dir)

    os.makedirs(args.cache_dir, exist_ok=True)
    enable_ai = getattr(args, "ai", "on") == "on"
    ai_workers = getattr(args, "ai_workers", 6)

    project_root = os.path.normpath(args.root_dir)
    analysis_paths = build_analysis_paths(args.cache_dir, project_root)
    analyse_dirs = getattr(args, "analyse_dirs", None)
    defines = getattr(args, "defines", None)

    # --- Globals ---
    global_vars = parser.extract_globals(project_root, analyse_dirs=analyse_dirs)
    with open(analysis_paths["globals"], "w", encoding="utf-8") as f:
        json.dump({"globals": global_vars}, f, indent=2, ensure_ascii=False)
    logger.info("Found %s global variables", len(global_vars))

    # --- Types ---
    types_data = parser.extract_types(
        project_root,
        args.cache_dir,
        enable_ai=enable_ai,
        ai_workers=ai_workers,
    )
    # --- Functions ---
    parser.extract_functions(
        project_root,
        output_json_path=analysis_paths["functions"],
        types_data=types_data,
        global_vars=global_vars,
        enable_ai=enable_ai,
        analyse_dirs=analyse_dirs,
        defines=defines,
        ai_workers=ai_workers,
    )

    logger.info(colorize_extract_phase_message("Analysis completed.", EXTRACT_PHASE_DONE_COLOR))

    # stamp the cache with the current version
    with open(version_file, "w") as _f:
        _f.write(VERSION)


def run_docgen_phase(args):
    """Generate documentation from cached extraction data.

    Pipeline: resolve args → load caches → filter → generate docs + appendix.
    All filtering happens at docgen time; cache JSONs stay unfiltered.
    """
    # ── Step 1: resolve generator and output format ──
    output_format = getattr(args, "format", "docx")
    generator = get_generator(output_format)

    logger.info(colorize_extract_phase_message("Generating docs...", EXTRACT_PHASE_START_COLOR))

    # ── Step 2: resolve paths (cache dir, root dir, analyse dirs, output folder) ──
    cache_dir = args.cache_dir
    root_dir = args.root_dir
    if hasattr(args, "analyse_dirs"):
        analyse_dirs = args.analyse_dirs
    else:
        analyse_dirs = [getattr(args, "analyse_dir", root_dir)]
    output_folder = args.output_folder

    # ── Step 3: build cache file paths and load types cache ──
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

    # ── Step 4: apply type filtering (--ignore-types, --ignore-kinds) ──
    ignore_types = getattr(args, "ignore_types", None)
    ignore_kinds = getattr(args, "ignore_kinds", [])
    if ignore_types or ignore_kinds:
        ignored_t = set(ignore_types or [])
        ignored_k = set(ignore_kinds or [])
        type_defs = types_data.get("type_definitions", {})
        for tname, tdef in list(type_defs.items()):
            if tname in ignored_t or tdef.get("kind") in ignored_k:
                type_defs.pop(tname, None)
                type_refs.pop(tname, None)

    # ── Step 5: load functions cache and filter by analyse_dirs ──
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

    # ── Step 6: apply call filtering (--ignore-calls) ──
    ignore_calls = getattr(args, "ignore_calls", None)
    if ignore_calls:
        ignored_c = set(ignore_calls)
        for func in selected_funcs:
            func["calls"] = [c for c in func.get("calls", []) if c not in ignored_c]

    # ── Step 7: scrub type_refs on ignored global-variable inputs ──
    ignore_types = getattr(args, "ignore_types", None)
    if ignore_types:
        ignored_t = set(ignore_types)
        for func in selected_funcs:
            for inp in func.get("inputs", []):
                if inp.get("kind") == "Global variable":
                    base = inp["type"].split()[-1].rstrip("*")
                    if base in ignored_t:
                        inp["type_ref"] = ""

    # ── Step 8: collect types referenced by selected functions' inputs ──
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

    # ── Step 9: configure generator options ──
    figures_dir = os.path.join(output_folder, "figures")
    graph_style = getattr(args, "style", "plain")

    _ALL_SECTION_KEYS = {
        "module_description", "module_summary", "inputs", "outputs",
        "global_data", "local_data", "algorithm", "interface", "appendix",
    }
    sections = getattr(args, "sections", None)
    if sections is None:
        sections = {k: True for k in _ALL_SECTION_KEYS}

    embedded_global_reference = getattr(args, "embedded_global_reference", "no") == "yes"
    language = getattr(args, "language", "c")
    out_param_location = getattr(args, "out_param_location", "inputs")

    # ── Step 10: render call-graph images (skip for table style) ──
    if graph_style != "table":
        generate_function_graphs(function_list=selected_funcs, output_dir=figures_dir, style=graph_style)

    # ── Step 11: generate per-function / per-file documents ──
    generator.generate_functions(
        function_list=selected_funcs,
        types_json=types_data,
        figures_dir=figures_dir,
        output_dir=output_folder,
        group_by=getattr(args, "group_by", "file"),
        style=graph_style,
        sections=sections,
        embedded_global_reference=embedded_global_reference,
        language=language,
        out_param_location=out_param_location,
    )

    # ── Step 12: generate project-wide appendix ──
    if sections.get("appendix", True):
        appendix_ext = get_format_extension(output_format)
        appendix_output = os.path.join(output_folder, f"appendix{appendix_ext}")
        generator.generate_appendix(types_data, appendix_output,
                                    filter_types=None,
                                    language=getattr(args, "language", "c"))

    logger.info(colorize_extract_phase_message("It's done.", EXTRACT_PHASE_DONE_COLOR))
