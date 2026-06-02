#!/usr/bin/env python3

import argparse
import logging
import os
import sys
from config.manager import ensure_ai_config_interactive, rerun_ai_config_interactive, set_config_value
from parsers import detect_language
from pipeline import run_extract_phase, run_docgen_phase
from core.utils import get_default_cache_dir


def configure_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    fmt = (
        "%(levelname)s %(name)s: %(message)s"
        if verbose
        else "%(levelname)s %(message)s"
    )
    logging.basicConfig(level=level, format=fmt, force=True)
    logging.getLogger("matplotlib").setLevel(logging.INFO)
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
    python -m cli generate examples/c
    python -m cli generate examples/c --lang c
    python -m cli generate examples/c --ai off
    python -m cli generate examples/c --analyse_dir examples/c/bsw --analyse_dir examples/c/drivers
    python -m cli generate examples/c --analyse_dir examples/c/comm/sensor.c --cache_dir .analysis --output_folder out_docs --ai on

  Configure AI:
    python -m cli config
    python -m cli config temperature 0.7
    python -m cli config max_tokens 1500
    python -m cli config retry_count 3
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
    python -m cli generate examples/c
    python -m cli generate examples/c --lang c
    python -m cli generate examples/c --ai off
    python -m cli generate examples/c --analyse_dir examples/c/bsw --analyse_dir examples/c/drivers
    python -m cli generate examples/c --analyse_dir examples/c/comm/sensor.c --cache_dir .analysis --output_folder out_docs --ai on
    python -m cli generate examples/c --group-by file --format markdown
"""

    generate_parser = subparsers.add_parser(
        "generate",
        help="Extract project data and generate markdown documentation",
        epilog=generate_examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    generate_parser.add_argument(
        "--lang",
        default="auto",
        help="Source language for parsing (auto-detected if not specified, default: auto)",
    )
    generate_parser.add_argument(
        "root_dir",
        help="Project root directory for the extract phase",
    )
    generate_parser.add_argument(
        "--analyse_dir",
        action="append",
        default=None,
        help="Subset of root_dir to generate docs for (repeatable, defaults to root_dir)",
    )
    generate_parser.add_argument(
        "--cache_dir",
        default=default_cache_dir,
        help="Cache directory for intermediate JSON files",
    )
    generate_parser.add_argument(
        "--output_folder",
        default="out",
        help="Output directory for markdown and figures",
    )
    generate_parser.add_argument(
        "--ai",
        choices=["on", "off"],
        default="off",
        help="Enable AI for type/function analysis and interactive onboarding when config is missing",
    )
    generate_parser.add_argument(
        "--format",
        choices=["markdown", "docx"],
        default="markdown",
        help="Output documentation format (default: markdown)",
    )
    generate_parser.add_argument(
        "--group-by",
        choices=["function", "file"],
        default="function",
        help="Generate one .md per function or per source file (default: function)",
    )
    generate_parser.add_argument(
        "--style",
        choices=["modern", "plain"],
        default="plain",
        help="Graph plotting style (default: plain)",
    )

    config_examples = """Examples:
    python -m cli config
    python -m cli --verbose config
    python -m cli config temperature 0.7
    python -m cli config max_tokens 1500
    python -m cli config retry_count 3
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

    analyse_dirs = cli_args.analyse_dir or [cli_args.root_dir]

    try:
        validate_paths(cli_args.root_dir, analyse_dirs)
    except ValueError as exc:
        parser.error(str(exc))

    if cli_args.command == "generate":
        if cli_args.ai == "on":
            ensure_ai_config_interactive()

        if cli_args.lang == "auto":
            cli_args.lang = detect_language(cli_args.root_dir)

        extract_args = argparse.Namespace(
            root_dir=cli_args.root_dir,
            cache_dir=cli_args.cache_dir,
            ai=cli_args.ai,
            language=cli_args.lang,
        )
        run_extract_phase(extract_args)

    # Document generation phase
    docgen_args = argparse.Namespace(
        root_dir=cli_args.root_dir,
        analyse_dirs=analyse_dirs,
        cache_dir=cli_args.cache_dir,
        output_folder=cli_args.output_folder,
        format=getattr(cli_args, "format", "markdown"),
        group_by=getattr(cli_args, "group_by", "function"),
        style=getattr(cli_args, "style", "plain"),
        language=cli_args.lang,
    )
    run_docgen_phase(docgen_args)


if __name__ == "__main__":
    main()
