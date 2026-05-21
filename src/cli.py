#!/usr/bin/env python3

import argparse
import logging
import os
import sys
from config_manager import ensure_ai_config_interactive, rerun_ai_config_interactive
from pipeline import build_analysis_paths, run_extract_phase, run_docgen_phase
from utils import get_default_cache_dir


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


def validate_paths(root_dir, analyse_dir):
    root_path = os.path.abspath(root_dir)
    analyse_path = os.path.abspath(analyse_dir)

    try:
        common_path = os.path.commonpath([root_path, analyse_path])
    except ValueError as exc:
        raise ValueError("analyse_dir must be inside root_dir") from exc

    if common_path != root_path:
        raise ValueError("analyse_dir must be inside root_dir")


def validate_write_cache_files(root_dir, cache_dir):
    analysis_paths = build_analysis_paths(cache_dir, root_dir)
    required_paths = [analysis_paths["types"], analysis_paths["functions"]]
    missing_paths = [path for path in required_paths if not os.path.exists(path)]
    if missing_paths:
        missing_text = ", ".join(missing_paths)
        raise ValueError(
            "write requires existing cache files: "
            f"{missing_text}. Run generate first."
        )


def normalize_argv(argv):
    if not argv:
        return argv

    global_options = {"--verbose"}
    insert_at = 0

    while insert_at < len(argv) and argv[insert_at] in global_options:
        insert_at += 1

    if insert_at >= len(argv):
        return argv

    if argv[insert_at] in {"generate", "write", "config", "-h", "--help"}:
        return argv

    if argv[insert_at].startswith("-"):
        return argv

    return [*argv[:insert_at], "generate", *argv[insert_at:]]


def build_parser(default_cache_dir):
    parser = argparse.ArgumentParser(
        description="Analyze C project, generate markdown docs, and manage AI configuration",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_examples = """Examples:
    python src/cli.py generate ATP_CODE
    python src/cli.py generate ATP_CODE --analyse_dir ATP_CODE/DMI
    python src/cli.py generate ATP_CODE --analyse_dir ATP_CODE/DMI/dmi_input.c --cache_dir .analysis --output_folder out_docs --ai on

Legacy form still works:
    python src/cli.py ATP_CODE --analyse_dir ATP_CODE/DMI
"""

    generate_parser = subparsers.add_parser(
        "generate",
        help="Extract project data and generate markdown documentation",
        epilog=generate_examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    generate_parser.add_argument(
        "root_dir",
        help="Project root directory for the extract phase",
    )
    generate_parser.add_argument(
        "--analyse_dir",
        default=None,
        help="Subset of root_dir to use for documentation generation (defaults to root_dir)",
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
        default="oo",
        help="Enable AI for type/function analysis and interactive onboarding when config is missing",
    )

    write_examples = """Examples:
    python src/cli.py write ATP_CODE/MT
    python src/cli.py write ATP_CODE --analyse_dir ATP_CODE/DMI --cache_dir .analysis --output_folder out_docs
    """

    write_parser = subparsers.add_parser(
        "write",
        help="Generate markdown documentation from existing cached analysis only",
        epilog=write_examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    write_parser.add_argument(
        "root_dir",
        help="Project root directory used to resolve cached analysis files",
    )
    write_parser.add_argument(
        "--analyse_dir",
        default=None,
        help="Subset of root_dir to use for documentation generation (defaults to root_dir)",
    )
    write_parser.add_argument(
        "--cache_dir",
        default=default_cache_dir,
        help="Cache directory for intermediate JSON files",
    )
    write_parser.add_argument(
        "--output_folder",
        default="out",
        help="Output directory for markdown and figures",
    )

    config_examples = """Examples:
    python src/cli.py config
    python src/cli.py --verbose config
    """

    subparsers.add_parser(
        "config",
        help="Run the interactive AI configuration onboarding flow",
        description="Rerun the interactive AI configuration onboarding flow, even if a config file already exists.",
        epilog=config_examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    return parser


def main():
    default_cache_dir = str(get_default_cache_dir())
    parser = build_parser(default_cache_dir)
    cli_args = parser.parse_args(normalize_argv(sys.argv[1:]))
    configure_logging(verbose=cli_args.verbose)

    if cli_args.command == "config":
        rerun_ai_config_interactive()
        return

    analyse_dir = cli_args.analyse_dir or cli_args.root_dir

    try:
        validate_paths(cli_args.root_dir, analyse_dir)
    except ValueError as exc:
        parser.error(str(exc))

    if cli_args.command == "generate":
        if cli_args.ai == "on":
            ensure_ai_config_interactive()

        # 1. 提取阶段（不调用AI）
        extract_args = argparse.Namespace(
            root_dir=cli_args.root_dir,
            cache_dir=cli_args.cache_dir,
            ai=cli_args.ai,
        )
        run_extract_phase(extract_args)
    elif cli_args.command == "write":
        try:
            validate_write_cache_files(cli_args.root_dir, cli_args.cache_dir)
        except ValueError as exc:
            parser.error(str(exc))

    # 2. 文档生成阶段（调用AI）
    docgen_args = argparse.Namespace(
        root_dir=cli_args.root_dir,
        analyse_dir=analyse_dir,
        cache_dir=cli_args.cache_dir,
        output_folder=cli_args.output_folder,
    )
    run_docgen_phase(docgen_args)


if __name__ == "__main__":
    main()
