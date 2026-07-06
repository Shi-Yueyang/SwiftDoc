# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build, Test & CLI Usage

See [README.md](README.md) for build, test, and CLI commands.

## Architecture

**Two-phase pipeline** orchestrated by `pipeline.py`:

1. **Extract phase** (`run_extract_phase`): Walks the source tree, parses source files with tree-sitter, extracts globals/types/functions, optionally enriches with AI descriptions, and writes JSON caches to the cache dir. Cache stores COMPLETE data — no filtering here.
2. **Docgen phase** (`run_docgen_phase`): Reads cached JSON, filters functions by `--analyse_dir`, applies `--ignore-calls`/`--ignore-types` filtering at docgen time (cache stays untainted), generates docs and call-graph PNGs.

**Parser plugin system** (`parsers/`): `BaseParser` is the ABC with `extract_functions()`, `extract_globals()`, and `extract_types()`. `CParser` and `AdaParser` are the implementations. New languages are registered via `parsers/__init__.py` → `register_parser()`.

**Generator plugin system** (`generators/`): Supports `markdown` and `docx` formats (default: `docx`). Modules must export `generate_functions()` and `generate_appendix()`. Registered in `generators/__init__.py`.

**AI integration** (`core/ai.py`): Uses the OpenAI SDK (compatible with any OpenAI-compatible API). Prompts are crafted in `ai_prompt_for_function()` and `ai_prompt_for_type()`. Retry with doubling `max_tokens` on empty responses. The `AI_FAILED` sentinel (`"ai failed"`) marks unrecoverable failures.

**C parsing** (`parsers/c/`): Three tree-sitter-based extractors:
- `globals.py` — walks declarations outside functions, distinguishes static/extern/definition
- `types.py` — regex-based extraction of typedefs/structs/unions/enums from `.h` files, with comment association
- `functions.py` — parses `.c` files for function definitions, resolves parameter types, pointer parameter directions (in/out/in out), global variable reads/writes (with direction), return types, and call relationships; builds `called_by` cross-references. Hardcoded call filter: `_IGNORED_CALLS = {"memcpy", "memset"}`.

**Change detection** (`core/compare.py`): `compare_functions()` and `compare_types()` diff fresh extractions against cached data using `normalized_body` (whitespace-stripped) or structural type keys. Only changed items trigger AI re-runs. Supports rename detection by matching bodies/structures across added/removed sets.

**Config** (`config/`):
- `manager.py` — AI config stored per-platform in `swift-doc/config.json` (Windows: `%APPDATA%\swift-doc\`, macOS: `~/Library/Application Support/swift-doc/`, Linux: `~/.config/swift-doc/`). Required keys: `api_key`, `base_url`, `model_name`. Optional: `temperature` (default 1.0), `max_tokens` (default 800), `retry_count` (default 1). `STATE_DIR` is the config directory path. `APP_DIR_NAME = "swift-doc"`.
- `toml_config.py` — Project-level TOML config (`swift-doc.toml`). `load_toml(path)` parses a config file, `find_config(dir)` looks for `swift-doc.toml` in a directory. `DEFAULT_CONFIG_NAME = "swift-doc.toml"`.

**Call-graph rendering** (`generators/images.py`): Two `--style` options:
- `"plain"` (default) — Pillow-rendered black/white, no shadows, sharp edges, thin lines
- `"table"` — embeds a two-column markdown/docx table (Callers | Callees) directly in the document. Self-calls are filtered out.

Long function names use `_wrap_text()` (underscore-aware line breaking) instead of truncation. Cards auto-size to fit wrapped text. Self-calls are stripped from callers/callees lists at render time.

**Data types** (`parsers/types.py`): TypedDict definitions for `GlobalVar`, `TypeDef`, `TypesData`, `FuncInput`, `FuncReturn`, `FuncDef` — these are the canonical shapes passed between parser, AI, compare, and generator modules.

## TOML Project Config (`swift-doc.toml`)

Placed in project root. Holds all CLI params. Resolution: **CLI args > TOML > built-in defaults**.

Discovery flow in `cli.py:_resolve_config_and_root()`:
- Positional ends with `.toml` → load that file, `root_dir` must be in TOML
- Positional is a file (e.g. `foo.c`) → parent dir = root_dir, file = auto `analyse_dir`
- Positional is a directory → use as root_dir, look for `swift-doc.toml` inside
- No positional → look for `swift-doc.toml` in CWD
- Nothing found → error and exit

Example:
```toml
root_dir = "examples/c"
lang = "c"
format = "docx"
group_by = "file"
style = "plain"
ai = "off"

[ignore]
calls = ["memcpy", "memset"]
types = ["noisy_type"]
kinds = []
```

CLI uses `argparse.SUPPRESS` for all moduledesign-command arguments so we can distinguish "not passed" from "passed with default value." Merge happens in `cli.py:_resolve()`.

## Ignore Filtering

- `--ignore-calls` / `[ignore] calls` — filters function names from `calls` lists (not `called_by`). Applied at **docgen time** — cache stores complete data.
- `--ignore-types` / `[ignore] types` — strips type names from `type_refs` and clears `type_ref` on global-variable inputs. Applied at **docgen time**.
- `--ignore-kinds` / `[ignore] kinds` — drops types whose `kind` field matches. C kinds: struct, union, enum, typedef. Ada kinds: record, enumeration, access, array, derived, subtype, modular, fixed_point, decimal_fixed_point, float, interface, private, type. Default: empty (no filtering). Applied at **docgen time**.
- Hardcoded baseline at extraction time: `_IGNORED_CALLS = {"memcpy", "memset"}` in `parsers/c/functions.py` — these are always filtered.

## Key Conventions

- Cache JSON files are named `{folder_name}_{global_variables|functions|global_types}.json` where `folder_name` is the basename of the project root.
- Function identity key is `(name, file)` tuple — allows static functions in different translation units to coexist.
- The `--ai` flag accepts `"on"` or `"off"` (default: `"off"`).
- Encoding: files are decoded with chardet detection; `gb18030` is the fallback for Chinese-encoded source.
- `examples/c/` is a sample C project used for both manual testing and as a reference.
- ANSI color output is gated on `sys.stderr.isatty()` for piped/redirected usage.
- Group-by default: `file` (one doc per source file). Format default: `docx`.

## Development Conventions

**Every bug fix must include a regression test.** Add it to the appropriate file under `tests/`. Match the existing test class and method naming style (`TestCamelCase`, `test_snake_case`). Use inline C code strings via `parse_c_code()` for unit tests, temp files via `tmp_dir`/`tmp_path` fixtures for file-level tests.

**Keep CLAUDE.md current.** After any significant change — new feature, renamed component, changed default, fixed a tricky bug — update this file so the next agent has accurate context.

**Run the full suite before declaring done.** `pytest tests/ -q` must pass. If changing defaults, check that no existing test silently depends on the old default.

**Verify end-to-end for behavior changes.** Run `swift-doc moduledesign examples/c --ai off` and inspect the output when touching extraction, generation, or filtering code. A passing unit test doesn't always catch a broken pipeline.

**Match existing patterns.** Follow the code style, naming, and structure already in the file you're editing. New test helpers mirror `parse_c_code()` / `find_first_function_node()` in `test_module_analysis.py`. New config keys follow the `OPTIONAL_CONFIG_JSON_MAP` pattern.

**Cache is source-of-truth.** Extraction produces complete, unfiltered data. Filtering (`--ignore-calls`, `--ignore-types`) happens at docgen time only. Never bake presentation concerns into the cache JSON.

**No backward-compatibility cruft.** Don't keep dual-mode APIs (file-path vs. in-memory) when only one mode has callers. If a parameter or code path is dead, delete it. Single-purpose, clean signatures over "might be useful later" flexibility.

**tree-sitter node identity is unreliable.** `node is other` and `node == other` can both fail. Always compare `start_byte` positions.

## Known Bugs

Historical bugs and patterns to watch are documented in [KNOWN_BUGS.md](KNOWN_BUGS.md).

## Communication Style

Speak warmly and naturally. Use affectionate words occasionally: dear, sweetie. Avoid repetition.
