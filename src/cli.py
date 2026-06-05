#!/usr/bin/env python3

import argparse
import logging
import os
import shutil
import sys
from config.manager import (
    ensure_ai_config_interactive,
    rerun_ai_config_interactive,
    set_config_value,
    STATE_DIR,
)
from config.toml_config import load_toml, find_config
from parsers import detect_language
from pipeline import run_extract_phase, run_docgen_phase
from core.utils import get_default_cache_dir


# -- built-in defaults for generate params (used when neither CLI nor TOML sets them) --
_DEFAULTS = {
    "lang": "auto",
    "output_folder": "out",
    "format": "docx",
    "group_by": "file",
    "style": "plain",
    "ai": "off",
}


def _last_cache_file():
    return os.path.join(STATE_DIR, "last_cache_dir")


def _read_last_cache_dir():
    path = _last_cache_file()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except (FileNotFoundError, OSError):
        return None


def _save_last_cache_dir(cache_dir):
    path = _last_cache_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(cache_dir))


def _resolve_config_and_root(cli_args):
    """Figure out config source and root_dir from CLI args.

    Returns (root_dir: str, toml_config: dict | None).
    Exits with an error message if nothing can be resolved.
    """
    positional = getattr(cli_args, "root_dir", None)
    toml_config = None

    if positional and positional.endswith(".toml"):
        # Explicit TOML config file
        if not os.path.isfile(positional):
            print(f"Error: config file not found: {positional}", file=sys.stderr)
            sys.exit(1)
        toml_config = load_toml(positional)
        root_dir = toml_config.get("root_dir")
        if not root_dir:
            print("Error: root_dir is required in TOML config", file=sys.stderr)
            sys.exit(1)
    elif positional and os.path.isfile(positional):
        # Single source file — treat parent dir as root, file as analyse_dir
        root_dir = os.path.dirname(os.path.abspath(positional))
        # Auto-discover swift-doc.toml from the parent dir
        config_path = find_config(root_dir)
        if config_path:
            toml_config = load_toml(config_path)
        # Set analyse_dirs to this single file (unless CLI already set it)
        if not hasattr(cli_args, "analyse_dir"):
            cli_args.analyse_dir = [os.path.abspath(positional)]
    elif positional:
        # Directory — look for swift-doc.toml inside
        if not os.path.isdir(positional):
            print(f"Error: directory not found: {positional}", file=sys.stderr)
            sys.exit(1)
        root_dir = positional
        config_path = find_config(root_dir)
        if config_path:
            toml_config = load_toml(config_path)
    else:
        # No positional — look for swift-doc.toml in CWD
        config_path = find_config(os.getcwd())
        if config_path:
            toml_config = load_toml(config_path)
            root_dir = toml_config.get("root_dir")
            if not root_dir:
                print("Error: root_dir is required in TOML config", file=sys.stderr)
                sys.exit(1)
        else:
            print("Error: no project directory or config specified.", file=sys.stderr)
            print("Usage: swift-doc generate <project_dir | config.toml>", file=sys.stderr)
            sys.exit(1)

    return root_dir, toml_config


def _resolve(key, cli_args, toml_config, default):
    """Resolve a single config value: CLI > TOML > built-in default."""
    cli_val = getattr(cli_args, key, None)
    if cli_val is not None:
        return cli_val
    if toml_config:
        tv = toml_config.get(key)
        if tv is not None:
            return tv
    return default


def configure_logging(verbose=False):
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


def validate_paths(root_dir, analyse_dirs):
    root_path = os.path.abspath(root_dir)
    for analyse_dir in analyse_dirs:
        analyse_path = os.path.abspath(analyse_dir)
        try:
            common_path = os.path.commonpath([root_path, analyse_path])
        except ValueError as exc:
            raise ValueError(f"analyse_dir must be inside root_dir: {analyse_dir}") from exc
        if common_path != root_path:
            raise ValueError(f"analyse_dir must be inside root_dir: {analyse_dir}")


def build_parser(default_cache_dir):
    examples = """Examples:
  Generate documentation:
    swift-doc generate examples/c
    swift-doc generate examples/c --lang c --style plain
    swift-doc generate my-config.toml
    swift-doc generate examples/c --analyse_dir examples/c/bsw --analyse_dir examples/c/drivers
    swift-doc generate examples/c --ignore-calls free --ignore-calls malloc

  Configure AI:
    swift-doc config
    swift-doc config temperature 0.7
    swift-doc config max_tokens 1500
    swift-doc config retry_count 3

  Clear cache:
    swift-doc clear-cache
    swift-doc clear-cache --cache_dir .analysis
"""
    parser = argparse.ArgumentParser(
        description="Analyze source code, generate documentation, and manage AI configuration",
        epilog=examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )

    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")

    generate_examples = """Examples:
    swift-doc generate examples/c
    swift-doc generate examples/c --lang c --style plain
    swift-doc generate my-config.toml
    swift-doc generate examples/c --analyse_dir examples/c/bsw --analyse_dir examples/c/drivers
    swift-doc generate examples/c --group-by file --format markdown
    swift-doc generate examples/c --ignore-calls free --ignore-calls malloc
"""

    generate_parser = subparsers.add_parser(
        "generate",
        help="Extract project data and generate documentation",
        epilog=generate_examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    generate_parser.add_argument(
        "root_dir",
        nargs="?",
        default=argparse.SUPPRESS,
        help="Project root directory or path to a TOML config file",
    )
    generate_parser.add_argument(
        "--lang",
        default=argparse.SUPPRESS,
        help="Source language for parsing (auto-detected if not specified, default: auto)",
    )
    generate_parser.add_argument(
        "--analyse_dir",
        action="append",
        default=argparse.SUPPRESS,
        help="Subset of root_dir to generate docs for (repeatable, defaults to root_dir)",
    )
    generate_parser.add_argument(
        "--cache_dir",
        default=argparse.SUPPRESS,
        help="Cache directory for intermediate JSON files",
    )
    generate_parser.add_argument(
        "--output_folder",
        default=argparse.SUPPRESS,
        help="Output directory for markdown and figures (default: out)",
    )
    generate_parser.add_argument(
        "--ai",
        choices=["on", "off"],
        default=argparse.SUPPRESS,
        help="Enable AI for type/function analysis (default: off)",
    )
    generate_parser.add_argument(
        "--format",
        choices=["markdown", "docx"],
        default=argparse.SUPPRESS,
        help="Output documentation format (default: docx)",
    )
    generate_parser.add_argument(
        "--group-by",
        choices=["function", "file"],
        default=argparse.SUPPRESS,
        help="Generate one doc per function or per source file (default: file)",
    )
    generate_parser.add_argument(
        "--style",
        choices=["plain", "slate", "fearless", "red", "table"],
        default=argparse.SUPPRESS,
        help="Graph plotting style (default: plain)",
    )
    generate_parser.add_argument(
        "--ignore-calls",
        action="append",
        default=argparse.SUPPRESS,
        help="Function names to exclude from call graphs (repeatable)",
    )
    generate_parser.add_argument(
        "--ignore-types",
        action="append",
        default=argparse.SUPPRESS,
        help="Type names to exclude from extraction (repeatable)",
    )
    generate_parser.add_argument(
        "--ignore-kinds",
        action="append",
        default=argparse.SUPPRESS,
        help="Type kinds to exclude: typedef, enum, struct, union (repeatable)",
    )

    config_examples = """Examples:
    swift-doc config
    swift-doc config temperature 0.7
    swift-doc config max_tokens 1500
    swift-doc config retry_count 3
    """

    config_parser = subparsers.add_parser(
        "config",
        help="Run the interactive AI configuration onboarding flow or set a config value directly",
        description="Rerun the interactive AI configuration onboarding flow, or set a specific config key to a value.",
        epilog=config_examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    config_parser.add_argument(
        "key",
        nargs="?",
        help="Config key to set (e.g., temperature, max_tokens, retry_count)",
    )
    config_parser.add_argument(
        "value",
        nargs="?",
        help="Config value to set",
    )

    clear_examples = """Examples:
    swift-doc clear-cache
    swift-doc clear-cache --cache_dir .analysis
"""

    clear_parser = subparsers.add_parser(
        "clear-cache",
        aliases=["clear"],
        help="Remove all cached analysis data",
        description="Clear all content in the cache directory.",
        epilog=clear_examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    clear_parser.add_argument(
        "--cache_dir",
        default=None,
        help="Cache directory to clear (default: last used, or platform cache dir)",
    )

    return parser


def main():
    default_cache_dir = str(get_default_cache_dir())
    parser = build_parser(default_cache_dir)
    cli_args = parser.parse_args(sys.argv[1:])
    configure_logging(verbose=cli_args.verbose)

    if cli_args.command == "config":
        if cli_args.key and cli_args.value:
            try:
                config_path = set_config_value(cli_args.key, cli_args.value)
                print(f"Config updated: {cli_args.key} = {cli_args.value}")
                print(f"Config file: {config_path}")
            except ValueError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                sys.exit(1)
        else:
            rerun_ai_config_interactive()
        return

    if cli_args.command in ("clear-cache", "clear"):
        cache_dir = getattr(cli_args, "cache_dir", None) or _read_last_cache_dir() or default_cache_dir
        if os.path.isdir(cache_dir):
            count = 0
            for entry in os.listdir(cache_dir):
                path = os.path.join(cache_dir, entry)
                try:
                    if os.path.isfile(path) or os.path.islink(path):
                        os.unlink(path)
                    else:
                        shutil.rmtree(path)
                    count += 1
                except OSError as exc:
                    print(f"Warning: could not remove {path}: {exc}", file=sys.stderr)
            print(f"Cleared {count} item(s) from {cache_dir}")
        else:
            print(f"Cache directory does not exist: {cache_dir}")
        return

    if cli_args.command == "generate":
        # -- resolve config source and root_dir --
        root_dir, toml_config = _resolve_config_and_root(cli_args)

        # -- merge: CLI > TOML > defaults --
        lang = _resolve("lang", cli_args, toml_config, _DEFAULTS["lang"])
        output_folder = _resolve("output_folder", cli_args, toml_config, _DEFAULTS["output_folder"])
        cache_dir = _resolve("cache_dir", cli_args, toml_config, default_cache_dir)
        fmt = _resolve("format", cli_args, toml_config, _DEFAULTS["format"])
        group_by = _resolve("group_by", cli_args, toml_config, _DEFAULTS["group_by"])
        style = _resolve("style", cli_args, toml_config, _DEFAULTS["style"])
        ai = _resolve("ai", cli_args, toml_config, _DEFAULTS["ai"])

        # analyse_dirs: CLI list > TOML list > [root_dir]
        cli_analyse = getattr(cli_args, "analyse_dir", None)
        toml_analyse = toml_config.get("analyse_dirs") if toml_config else None
        analyse_dirs = cli_analyse or toml_analyse or [root_dir]

        # ignore sets: CLI list > TOML list
        cli_ignore_calls = getattr(cli_args, "ignore_calls", None)
        toml_ignore_calls = toml_config.get("ignore_calls") if toml_config else None
        ignore_calls = set(cli_ignore_calls or toml_ignore_calls or [])

        cli_ignore_types = getattr(cli_args, "ignore_types", None)
        toml_ignore_types = toml_config.get("ignore_types") if toml_config else None
        ignore_types = set(cli_ignore_types or toml_ignore_types or [])

        cli_ignore_kinds = getattr(cli_args, "ignore_kinds", None)
        toml_ignore_kinds = toml_config.get("ignore_kinds") if toml_config else None
        ignore_kinds = cli_ignore_kinds or toml_ignore_kinds or []

        # -- validate --
        try:
            validate_paths(root_dir, analyse_dirs)
        except ValueError as exc:
            parser.error(str(exc))

        # -- AI onboarding if needed --
        if ai == "on":
            ensure_ai_config_interactive()

        # -- language detection --
        if lang == "auto":
            lang = detect_language(root_dir)

        # -- extract phase --
        extract_args = argparse.Namespace(
            root_dir=root_dir,
            cache_dir=cache_dir,
            ai=ai,
            language=lang,
        )
        run_extract_phase(extract_args)

        # -- docgen phase --
        docgen_args = argparse.Namespace(
            root_dir=root_dir,
            analyse_dirs=analyse_dirs,
            cache_dir=cache_dir,
            output_folder=output_folder,
            format=fmt,
            group_by=group_by,
            style=style,
            language=lang,
            ignore_calls=ignore_calls,
            ignore_types=ignore_types,
            ignore_kinds=ignore_kinds,
        )
        run_docgen_phase(docgen_args)

        # -- remember cache dir for clear-cache --
        _save_last_cache_dir(cache_dir)


if __name__ == "__main__":
    main()
