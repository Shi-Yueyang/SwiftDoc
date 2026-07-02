#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Comparison utilities for detecting added/modified/removed functions and types
between cached and freshly-extracted analysis data.
"""

import logging


logger = logging.getLogger(__name__)

_STRUCTURAL_TYPE_KEYS = frozenset({"kind", "members", "values", "original_type"})


def _signature_changed(old_func, new_func):
    """Return True if the function signature (parameters or return type) changed.

    Compares return_type and the parameter list (name, type, direction),
    ignoring global-variable inputs which are derived from the body.
    """
    if old_func.get("return_type") != new_func.get("return_type"):
        return True

    def _param_key(inp):
        return (inp.get("name"), inp.get("type"), inp.get("direction"))

    old_params = sorted(
        _param_key(i) for i in old_func.get("inputs", [])
        if i.get("kind") == "parameter"
    )
    new_params = sorted(
        _param_key(i) for i in new_func.get("inputs", [])
        if i.get("kind") == "parameter"
    )
    return old_params != new_params


def compare_functions(old_funcs, new_funcs):
    """Compare two function lists and return added, modified, and removed.

    Keys functions by (name, file) so that static helpers with the same
    name in different translation units don't collide.

    Also detects renames: if a function is removed and another with
    identical normalized_body is added, transfers AI descriptions.
    """
    old_dict = {(f["name"], f.get("file", "")): f for f in old_funcs}
    new_dict = {(f["name"], f.get("file", "")): f for f in new_funcs}

    added = []
    modified = []
    removed = []
    renames = []

    old_keys = set(old_dict.keys())
    new_keys = set(new_dict.keys())

    matched_new = set()

    for key in sorted(old_keys | new_keys):
        old_func = old_dict.get(key)
        new_func = new_dict.get(key)
        if old_func is None:
            added.append(new_func)
            matched_new.add(key)
        elif new_func is None:
            removed.append(old_func)
        else:
            matched_new.add(key)
            old_body = old_func.get("normalized_body", "")
            new_body = new_func.get("normalized_body", "")
            if old_body != new_body or _signature_changed(old_func, new_func):
                modified.append({"old": old_func, "new": new_func})

    # Rename correlation: if a removed function has the same normalized_body
    # as a newly-added function, transfer AI descriptions.
    removed_by_body = {}
    for func in removed:
        body = func.get("normalized_body", "")
        if body:
            removed_by_body.setdefault(body, []).append(func)

    for func in added:
        if (func["name"], func.get("file", "")) in matched_new:
            body = func.get("normalized_body", "")
            candidates = removed_by_body.get(body, [])
            if candidates:
                old = candidates.pop(0)
                if old["name"] == func["name"]:
                    continue  # same name, different file — not a rename
                for field in ("module_summary", "algorithm_logic", "inputs_description", "return_description"):
                    if old.get(field) and not func.get(field):
                        func[field] = old[field]
                func["_renamed_from"] = old.get("_renamed_from", old["name"])
                logger.info("Renamed function: %s -> %s (transferred descriptions)", old["name"], func["name"])

    return {"added": added, "modified": modified, "removed": removed}


def compare_types(old_types, new_types):
    """Compare two type-definition dicts and return added, modified, and removed.

    Only structural keys (kind, members, values, original_type) are compared.
    source_file and comment changes are ignored — they don't trigger AI re-runs.

    Rename correlation: if a type is removed and another of the same kind
    with identical members/values is added, transfers type_description.
    """
    added = {}
    modified = {}
    removed = {}

    all_names = set(old_types.keys()) | set(new_types.keys())
    for name in sorted(all_names):
        old_def = old_types.get(name)
        new_def = new_types.get(name)
        if old_def is None:
            added[name] = dict(new_def)
        elif new_def is None:
            removed[name] = dict(old_def)
        else:
            old_core = {k: v for k, v in old_def.items() if k in _STRUCTURAL_TYPE_KEYS}
            new_core = {k: v for k, v in new_def.items() if k in _STRUCTURAL_TYPE_KEYS}
            if old_core != new_core:
                modified[name] = dict(new_def)

    # Rename correlation: match removed types to added types by kind + structure
    for old_name, old_def in list(removed.items()):
        old_core = {k: v for k, v in old_def.items() if k in _STRUCTURAL_TYPE_KEYS}
        if not old_core:
            continue
        for new_name, new_def in list(added.items()):
            new_core = {k: v for k, v in new_def.items() if k in _STRUCTURAL_TYPE_KEYS}
            if old_core == new_core and old_def.get("kind") == new_def.get("kind"):
                if old_name == new_name:
                    continue
                new_def["type_description"] = old_def.get("type_description", "")
                new_def["_renamed_from"] = old_def.get("_renamed_from", old_name)
                removed.pop(old_name)
                added[new_name] = new_def
                logger.info("Renamed type: %s -> %s (transferred description)", old_name, new_name)
                break

    return {"added": added, "modified": modified, "removed": removed}
