#!/usr/bin/env python3
# analyze.py
import argparse
from pipeline import run_extract_phase, run_docgen_phase


def build_parser():
    examples = """Examples:
    python src/cli.py src/module
    python src/cli.py src --analyse_dir src/module
    python src/cli.py src/module --cache_dir .analysis --output_folder out_docs --ai off
"""

    parser = argparse.ArgumentParser(
        description="Analyze C project and generate markdown docs",
        epilog=examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "root_dir",
        help="Module directory or single .c file for documentation generation",
    )
    parser.add_argument(
        "--analyse_dir",
        default=None,
        help="Project root directory for extract phase (defaults to root_dir)",
    )
    parser.add_argument(
        "--cache_dir",
        default=".analysis",
        help="Cache directory for intermediate JSON files",
    )
    parser.add_argument(
        "--output_folder",
        default="out",
        help="Output directory for markdown and figures",
    )
    parser.add_argument(
        "--ai",
        choices=["on", "off"],
        default="on",
        help="Enable AI for doc generation updates",
    )
    return parser


def main():
    parser = build_parser()
    cli_args = parser.parse_args()
    analyse_dir = cli_args.analyse_dir or cli_args.root_dir

    #1. 提取阶段（不调用AI）
    extract_args = argparse.Namespace(
        source_dir=analyse_dir,
        cache_dir=cli_args.cache_dir,
    )
    run_extract_phase(extract_args)

    # 2. 文档生成阶段（调用AI）
    docgen_args = argparse.Namespace(
        source_dir=analyse_dir,
        module_dir=cli_args.root_dir,
        cache_dir=cli_args.cache_dir,
        output_folder=cli_args.output_folder,
        ai=cli_args.ai,
    )
    run_docgen_phase(docgen_args)


if __name__ == "__main__":
    main()
