#!/usr/bin/env python3

import logging
import os
import sys
from types import SimpleNamespace

from config.manager import ensure_ai_config_interactive
from config.toml_config import load_toml
from _version import VERSION
from pipeline import run_extract_phase, run_docgen_phase
from core.utils import get_default_cache_dir


USAGE = f"""\
swift-doc {VERSION} - C code analysis that generates documentation with call graphs.

Usage:
  swift-doc <config.toml>

All options live in the TOML config file; there are no CLI flags.
Relative paths in the config (root_dir, output_folder, cache_dir) resolve
against the config file's directory, so drag-and-drop onto the exe works.
"""

# -- built-in defaults for generate params (used when TOML doesn't set them) --
_DEFAULTS = {
    "output_folder": "out",
    "format": "docx",
    "group_by": "file",
    "style": "plain",
    "ai": "off",
    "ai_workers": 6,
    "embedded_global_reference": "no",
    "out_param_location": "inputs",
}

# Valid values per option key, validated after TOML resolution.
_CHOICES = {
    "format": ("markdown", "docx"),
    "group_by": ("function", "file"),
    "style": ("plain", "slate", "fearless", "red", "table"),
    "ai": ("on", "off"),
    "embedded_global_reference": ("yes", "no"),
    "out_param_location": ("inputs", "outputs"),
}


def _fail(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


def configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = (
        "%(levelname)s %(name)s: %(message)s"
        if verbose
        else "%(levelname)s %(message)s"
    )
    logging.basicConfig(level=level, format=fmt, force=True)
    logging.getLogger("PIL").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def validate_paths(root_dir: str, analyse_dirs: list) -> None:
    root_path = os.path.abspath(root_dir)
    for analyse_dir in analyse_dirs:
        analyse_path = os.path.abspath(analyse_dir)
        try:
            common_path = os.path.commonpath([root_path, analyse_path])
        except ValueError as exc:
            raise ValueError(f"analyse_dir must be inside root_dir: {analyse_dir}") from exc
        if common_path != root_path:
            raise ValueError(f"analyse_dir must be inside root_dir: {analyse_dir}")


def _resolve_relative(value: str, base_dir: str) -> str:
    """Resolve *value* against *base_dir* unless it is already absolute."""
    if os.path.isabs(value):
        return os.path.normpath(value)
    return os.path.normpath(os.path.join(base_dir, value))


def run_from_config(config_path: str) -> None:
    """Load the TOML config at *config_path* and run extract + docgen phases.

    The TOML config is the only source of options — relative paths in it are
    resolved against the config file's directory (root_dir, output_folder,
    cache_dir) or against root_dir (analyse_dirs).
    """
    toml_config = load_toml(config_path)

    doc_type = toml_config.get("type")
    if doc_type != "moduledesign":
        _fail(f"unknown document type '{doc_type}' in {config_path}")

    config_dir = os.path.dirname(os.path.abspath(config_path))

    root_dir = toml_config.get("root_dir")
    if not root_dir:
        _fail(f"root_dir is required in {config_path}")
    root_dir = _resolve_relative(root_dir, config_dir)

    configure_logging(verbose=bool(toml_config.get("verbose")))

    # Resolve every option that has a built-in default, then validate.
    options = {}
    for key, default in _DEFAULTS.items():
        if key in ("output_folder",):
            continue
        options[key] = toml_config.get(key) or default
    for key, allowed in _CHOICES.items():
        if options[key] not in allowed:
            _fail(
                f"invalid {key} = '{options[key]}' in {config_path}"
                f" (allowed: {', '.join(allowed)})"
            )

    output_folder = _resolve_relative(
        toml_config.get("output_folder") or _DEFAULTS["output_folder"], config_dir)
    cache_dir = _resolve_relative(
        toml_config.get("cache_dir") or str(get_default_cache_dir()), config_dir)

    analyse_dirs = toml_config.get("analyse_dirs") or [root_dir]
    analyse_dirs = [_resolve_relative(d, root_dir) for d in analyse_dirs]

    ignore_calls = set(toml_config.get("ignore_calls") or [])
    ignore_types = set(toml_config.get("ignore_types") or [])
    ignore_kinds = toml_config.get("ignore_kinds") or []
    defines = set(toml_config.get("define_macros") or [])
    sections = toml_config.get("sections") or {}

    try:
        validate_paths(root_dir, analyse_dirs)
    except ValueError as exc:
        _fail(str(exc))

    if options["ai"] == "on":
        ensure_ai_config_interactive()

    try:
        ai_workers = int(options["ai_workers"])
    except ValueError:
        _fail(f"ai_workers must be an integer in {config_path}, got '{options['ai_workers']}'")

    extract_args = SimpleNamespace(
        root_dir=root_dir,
        cache_dir=cache_dir,
        ai=options["ai"],
        ai_workers=ai_workers,
        analyse_dirs=analyse_dirs,
        defines=defines,
    )
    run_extract_phase(extract_args)

    docgen_args = SimpleNamespace(
        root_dir=root_dir,
        analyse_dirs=analyse_dirs,
        cache_dir=cache_dir,
        output_folder=output_folder,
        format=options["format"],
        group_by=options["group_by"],
        style=options["style"],
        ignore_calls=ignore_calls,
        ignore_types=ignore_types,
        ignore_kinds=ignore_kinds,
        sections=sections,
        embedded_global_reference=options["embedded_global_reference"],
        out_param_location=options["out_param_location"],
    )
    run_docgen_phase(docgen_args)

    print(f"Docs written to: {output_folder}")


def main() -> None:
    args = sys.argv[1:]

    if not args:
        print(USAGE, file=sys.stderr)
        sys.exit(1)
    if args[0] in ("-h", "--help"):
        print(USAGE)
        return
    if len(args) > 1:
        print(USAGE, file=sys.stderr)
        _fail(f"unexpected arguments: {' '.join(args[1:])} - all options belong in the TOML config")

    config_path = args[0]
    if not config_path.endswith(".toml"):
        print(USAGE, file=sys.stderr)
        _fail(f"expected a .toml config file, got: {config_path}")
    if not os.path.isfile(config_path):
        _fail(f"config file not found: {config_path}")

    run_from_config(config_path)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        sys.exit(130)
