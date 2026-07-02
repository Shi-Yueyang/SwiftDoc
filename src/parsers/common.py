"""Shared cache I/O, AI enrichment, and refresh logic for language parsers.

Both C and Ada parsers import from here to avoid duplicating ~400 lines of
identical cache management and AI orchestration code.
"""

import os
import re
import json
import time
import logging
import tempfile
import copy

from core.ai import ai_prompt_for_function, ai_prompt_for_type, call_ai_from_config, AI_FAILED
from core.compare import compare_functions, compare_types
from core.utils import build_cache_name, highlight_message

logger = logging.getLogger(__name__)
AI_RESULT_PREVIEW_CHARS = 24


# ── function cache I/O ──────────────────────────────────────────────────────

def load_previous_function_cache(output_json_path):
    if os.path.exists(output_json_path):
        try:
            with open(output_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("functions", [])
            return data, output_json_path
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to load previous function cache from %s", output_json_path)
    return {"functions": []}, None


def write_function_cache(output_json_path, output_data):
    os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=os.path.dirname(output_json_path), delete=False
    ) as tmp_file:
        json.dump(output_data, tmp_file, indent=2, ensure_ascii=False)
        tmp_path = tmp_file.name
    os.replace(tmp_path, output_json_path)


# ── type cache I/O ──────────────────────────────────────────────────────────

def load_previous_type_cache(cache_path, default_description=""):
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("description", default_description)
            data.setdefault("type_definitions", {})
            data.setdefault("type_references", {})
            return data, cache_path
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to load previous type cache from %s", cache_path)
    return {"description": default_description, "type_definitions": {}, "type_references": {}}, None


def write_types_cache(cache_path, master_data):
    master_types = master_data.get("type_definitions", {})
    sorted_names = sorted(master_types.keys())
    master_data["type_references"] = {
        name: f"A_{idx+1}" for idx, name in enumerate(sorted_names)
    }
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=os.path.dirname(cache_path), delete=False
    ) as tmp_file:
        json.dump(master_data, tmp_file, indent=2, ensure_ascii=False)
        tmp_path = tmp_file.name
    os.replace(tmp_path, cache_path)


# ── function metadata / AI ──────────────────────────────────────────────────

def prepare_function_metadata(func, type_descriptions=None):
    func["algorithm_logic"] = func.get("algorithm_logic", "")
    func["module_summary"] = func.get("module_summary", "")

    if (
        isinstance(func.get("returns"), list)
        and func["returns"]
        and isinstance(func["returns"][0], str)
    ):
        func["returns"] = [
            {"expression": expr, "return_description": ""} for expr in func["returns"]
        ]
    else:
        for ret in func.get("returns", []):
            ret["return_description"] = ret.get("return_description", "")

    for inp in func.get("inputs", []):
        inp["inputs_description"] = inp.get("inputs_description", "")
        if inp.get("kind") == "Global variable":
            base_type_match = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", inp["type"])
            base_type = base_type_match.group(1) if base_type_match else inp["type"]
            inp["type_description"] = (type_descriptions or {}).get(base_type, "")


def enrich_function_with_ai(func, type_descriptions, language="c"):
    prepare_function_metadata(func, type_descriptions)
    prompt = ai_prompt_for_function(func, language=language)
    response = call_ai_from_config(prompt)
    if response != AI_FAILED:
        try:
            desc = json.loads(response)
            func["module_summary"] = desc.get("module_summary", "")
            func["algorithm_logic"] = desc.get("algorithm_logic", "")
            param_descs = {
                item["name"]: item.get("inputs_description", "")
                for item in desc.get("inputs_description", [])
            }
            for inp in func.get("inputs", []):
                inp["inputs_description"] = param_descs.get(inp["name"], inp.get("inputs_description", ""))
            return_descs = desc.get("return_values", [])
            for idx, ret_item in enumerate(func.get("returns", [])):
                ret_item["return_description"] = return_descs[idx] if idx < len(return_descs) else ""
        except json.JSONDecodeError as exc:
            logger.debug("JSON parse failed: %s", exc)
            func["algorithm_logic"] = AI_FAILED
    else:
        func["algorithm_logic"] = AI_FAILED
    return func["algorithm_logic"]


def summarize_ai_result(description):
    normalized = " ".join(str(description).split())
    success = normalized != AI_FAILED
    preview = normalized[:AI_RESULT_PREVIEW_CHARS]
    if len(normalized) > AI_RESULT_PREVIEW_CHARS:
        preview = f"{preview}..."
    return "success" if success else "failed", preview


def is_missing_algorithm_logic(func):
    logic = func.get("algorithm_logic")
    if not isinstance(logic, str) or not logic.strip():
        return True
    if logic == AI_FAILED:
        return True
    # module_summary is generated in the same AI call — if the AI call
    # previously failed, the summary will also be missing/failed, so
    # re-run.  But don't force a re-run just because an old cache
    # predates the module_summary field.
    summary = func.get("module_summary")
    if isinstance(summary, str) and summary == AI_FAILED:
        return True
    return False


# ── type AI ─────────────────────────────────────────────────────────────────

def enrich_type_definition(type_name, type_definition, language="c"):
    prompt = ai_prompt_for_type(type_name, type_definition, language=language)
    description = call_ai_from_config(prompt)
    type_definition["type_description"] = description
    if description == AI_FAILED:
        logger.debug("Marked type as AI failed: %s", type_name)
    else:
        logger.debug("Generated AI description for type: %s", type_name)
    return type_definition["type_description"]


def is_missing_type_description(type_definition):
    description = type_definition.get("type_description")
    if not isinstance(description, str) or not description.strip():
        return True
    return description == AI_FAILED


# ── refresh orchestrators ───────────────────────────────────────────────────

def refresh_functions(all_functions, output_json_path, types_data, enable_ai=True, language="c"):
    """Compare fresh functions against cache, apply AI enrichment for changes."""
    type_descriptions = {
        name: info["type_description"]
        for name, info in types_data.get("type_definitions", {}).items()
        if isinstance(info, dict) and "type_description" in info
    }
    previous_data, loaded_from = load_previous_function_cache(output_json_path)
    previous_functions = previous_data.get("functions", [])

    def _func_key(f):
        return (f["name"], f["file"])

    diff = compare_functions(previous_functions, all_functions)

    added = diff.get("added", [])
    modified = diff.get("modified", [])
    removed = diff.get("removed", [])
    changed_functions = [*added, *(item["new"] for item in modified)]

    total_changes = len(added) + len(modified) + len(removed)
    if total_changes:
        logger.info("Compared to cache: %s function(s) changed (%s added, %s modified, %s removed)",
                    total_changes, len(added), len(modified), len(removed))
    else:
        logger.info("Compared to cache: no function changes detected")

    if enable_ai:
        missing_logic_keys = {
            _func_key(func)
            for func in previous_functions
            if is_missing_algorithm_logic(func)
        }
        changed_map = {_func_key(f): f for f in changed_functions}
        for func in all_functions:
            if _func_key(func) in missing_logic_keys:
                changed_map[_func_key(func)] = func
        changed_functions = list(changed_map.values())

    output_data = {"functions": copy.deepcopy(previous_functions)}
    function_map = {_func_key(f): f for f in output_data["functions"]}

    for func in removed:
        key = _func_key(func)
        if key in function_map:
            del function_map[key]
            logger.debug("Removed function: %s (%s)", func["name"], func.get("file"))

    for func in changed_functions:
        fresh_function = copy.deepcopy(func)
        if not enable_ai:
            fresh_function["algorithm_logic"] = ""
        prepare_function_metadata(fresh_function, type_descriptions)
        function_map[_func_key(fresh_function)] = fresh_function

    should_persist = bool(
        changed_functions or removed or loaded_from != output_json_path
        or not os.path.exists(output_json_path)
    )

    if enable_ai:
        if changed_functions:
            logger.info(highlight_message("Refreshing AI descriptions for %s changed functions"), len(changed_functions))
        else:
            logger.info(highlight_message("No functions require AI refresh"))
        for idx, func in enumerate(changed_functions, start=1):
            current = function_map[_func_key(func)]
            description = enrich_function_with_ai(current, type_descriptions, language=language)
            status, preview = summarize_ai_result(description)
            logger.info("AI progress %s/%s: %s [%s] %s", idx, len(changed_functions), current["name"], status, preview)
            output_data["functions"] = list(function_map.values())
            write_function_cache(output_json_path, output_data)
            time.sleep(0.5)
    elif should_persist:
        output_data["functions"] = list(function_map.values())
        write_function_cache(output_json_path, output_data)

    if enable_ai and not changed_functions and should_persist:
        output_data["functions"] = list(function_map.values())
        write_function_cache(output_json_path, output_data)

    logger.debug("Added: %s functions", len(added))
    logger.debug("Modified: %s functions", len(modified))
    logger.debug("Removed: %s functions", len(removed))
    logger.debug("Total functions: %s", len(function_map))
    logger.debug("All functions saved to %s", output_json_path)

    return output_json_path


def refresh_type_definitions(fresh_types, project_dir, output_dir=".analysis", enable_ai=True,
                            language="c"):
    """Compare fresh types against cache, apply AI enrichment for changes."""
    folder_name = build_cache_name(project_dir)
    cache_path = os.path.join(output_dir, f"{folder_name}_global_types.json")
    previous_data, loaded_from = load_previous_type_cache(cache_path)
    previous_types = previous_data.get("type_definitions", {})
    diff = compare_types(previous_types, fresh_types)

    added = diff.get("added", {})
    modified = diff.get("modified", {})
    removed = diff.get("removed", {})
    changed_names = sorted(set(added.keys()) | set(modified.keys()))
    if enable_ai:
        missing_desc_names = {
            name
            for name, defn in fresh_types.items()
            if is_missing_type_description(previous_types.get(name, {}))
        }
        changed_names = sorted(set(changed_names) | missing_desc_names)

    total_type_changes = len(added) + len(modified) + len(removed)
    if total_type_changes:
        logger.info("Compared to cache: %s type(s) changed (%s added, %s modified, %s removed)",
                    total_type_changes, len(added), len(modified), len(removed))
    else:
        logger.info("Compared to cache: no type changes detected")

    logger.debug("Type changes: added=%s modified=%s removed=%s", len(added), len(modified), len(removed))

    master_data = {
        "description": "",
        "type_definitions": copy.deepcopy(previous_types),
        "type_references": previous_data.get("type_references", {}),
    }
    master_types = master_data["type_definitions"]

    for type_name in removed.keys():
        if type_name in master_types:
            del master_types[type_name]
            logger.debug("Removed type: %s", type_name)

    for type_name in changed_names:
        fresh_definition = copy.deepcopy(
            modified.get(type_name) or added.get(type_name) or fresh_types[type_name]
        )
        if not enable_ai:
            fresh_definition["type_description"] = ""
            logger.debug("Left description empty for type without AI: %s", type_name)
        master_types[type_name] = fresh_definition

    should_persist = bool(
        changed_names or removed or loaded_from != cache_path or not os.path.exists(cache_path)
    )

    if enable_ai:
        if changed_names:
            logger.info(highlight_message("Refreshing AI descriptions for %s changed types"), len(changed_names))
        else:
            logger.info(highlight_message("No types require AI refresh"))
        for idx, type_name in enumerate(changed_names, start=1):
            description = enrich_type_definition(type_name, master_types[type_name], language=language)
            status, preview = summarize_ai_result(description)
            logger.info("AI progress %s/%s: %s [%s] %s", idx, len(changed_names), type_name, status, preview)
            write_types_cache(cache_path, master_data)
            time.sleep(0.15)
    elif should_persist:
        write_types_cache(cache_path, master_data)

    if enable_ai and not changed_names and should_persist:
        write_types_cache(cache_path, master_data)

    logger.debug("Added: %s types", len(added))
    logger.debug("Modified: %s types", len(modified))
    logger.debug("Removed: %s types", len(removed))
    logger.debug("Type definitions saved to %s", cache_path)
    logger.debug("Total types found: %s", len(master_types))
    return master_data
