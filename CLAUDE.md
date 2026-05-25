# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

```bash
# Install in editable mode
pip install -e .

# Run tests
pytest tests/ -v

# Run a single test file or test
pytest tests/test_extract_globals.py -v
pytest tests/test_extract_globals.py::TestCollectGlobalsFromCFile::test_finds_global_variables -v

# Build standalone executable
pip install pyinstaller
pyinstaller --name auto-md --onefile --clean --paths src src/cli.py
```

Run the CLI:
```bash
python -m cli generate c examples/c --ai off
python -m cli config                          # interactive AI setup
python -m cli config temperature 0.7          # set individual config values
```

## Architecture

**Two-phase pipeline** orchestrated by `pipeline.py`:

1. **Extract phase** (`run_extract_phase`): Walks the source tree, parses C files with tree-sitter, extracts globals/types/functions, optionally enriches with AI descriptions, and writes JSON caches to the cache dir.
2. **Docgen phase** (`run_docgen_phase`): Reads cached JSON, filters functions by `--analyse_dir`, generates markdown docs and call-graph PNGs.

**Parser plugin system** (`parsers/`): `BaseParser` is the ABC with `extract_functions()`, `extract_globals()`, and `extract_types()`. `CParser` is the only implementation. New languages are registered via `parsers/__init__.py` → `register_parser()`.

**Generator plugin system** (`generators/`): Modules are imported by format name. Only `markdown` exists today. Must export `generate_functions()` and `generate_appendix()`. Registered in `generators/__init__.py`.

**AI integration** (`core/ai.py`): Uses the OpenAI SDK (compatible with any OpenAI-compatible API). Prompts are crafted in `ai_prompt_for_function()` and `ai_prompt_for_type()`. Retry with doubling `max_tokens` on empty responses. The `AI_FAILED` sentinel (`"ai failed"`) marks unrecoverable failures.

**C parsing** (`parsers/c/`): Three tree-sitter-based extractors:
- `globals.py` — walks declarations outside functions, distinguishes static/extern/definition
- `types.py` — regex-based extraction of typedefs/structs/unions/enums from `.h` files, with comment association
- `functions.py` — parses `.c` files for function definitions, resolves parameter types, global variable reads/writes, and call relationships; builds `called_by` cross-references

**Change detection** (`core/compare.py`): `compare_functions()` and `compare_types()` diff fresh extractions against cached data using `normalized_body` (whitespace-stripped) or structural type keys. Only changed items trigger AI re-runs. Supports rename detection by matching bodies/structures across added/removed sets.

**Config** (`config/manager.py`): User config stored per-platform (Windows: `%APPDATA%\aoto-md\config.json`, macOS: `~/Library/Application Support/aoto-md/config.json`, Linux: `~/.config/aoto-md/config.json`). Required keys: `api_key`, `base_url`, `model_name`. Optional: `temperature` (default 1.0), `max_tokens` (default 800), `retry_count` (default 1).

**Data types** (`parsers/types.py`): TypedDict definitions for `GlobalVar`, `TypeDef`, `TypesData`, `FuncInput`, `FuncReturn`, `FuncDef` — these are the canonical shapes passed between parser, AI, compare, and generator modules.

## Key Conventions

- Cache JSON files are named `{folder_name}_{globals|functions|global_types}.json` where `folder_name` is the basename of the project root.
- Function identity key is `(name, file)` tuple — this allows static functions in different translation units to coexist.
- The `--ai` flag accepts `"on"` or `"oo"` (a typo preserved as the default meaning "off").
- Encoding: files are decoded with chardet detection; `gb18030` is the fallback for Chinese-encoded source.
- `examples/c/` is a sample C project used for both manual testing and as a reference.
- ANSI color output is gated on `sys.stderr.isatty()` for piped/redirected usage.
