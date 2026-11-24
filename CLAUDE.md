# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build, Test & CLI Usage

See [README.md](README.md) for build, test, and CLI commands.

## Architecture

**Two-phase pipeline** orchestrated by `pipeline.py`:

1. **Extract phase** (`run_extract_phase`): Walks the source tree, parses source files with tree-sitter, extracts globals/types/functions, optionally enriches with AI descriptions, and writes JSON caches to the cache dir. Cache stores COMPLETE data — no filtering here.
2. **Docgen phase** (`run_docgen_phase`): Reads cached JSON, filters functions by `analyse_dirs`, applies `ignore_calls`/`ignore_types` filtering at docgen time (cache stays untainted), generates docs and call-graph PNGs.

**Parsers** (`parsers/`): swift-doc is C-only. `CParser` (`parsers/c/`, re-exported from `parsers/__init__.py`) provides `extract_functions()`, `extract_globals()`, and `extract_types()`; `pipeline.run_extract_phase` instantiates it directly. There is no language registry or `--lang` flag.

**Generator plugin system** (`generators/`): Supports `markdown` and `docx` formats (default: `docx`). Modules must export `generate_functions()` and `generate_appendix()`. Registered in `generators/__init__.py`.

**AI integration** (`core/ai.py`): Uses the OpenAI SDK (compatible with any OpenAI-compatible API). Prompts are crafted in `ai_prompt_for_function()` and `ai_prompt_for_type()`. Retry with doubling `max_tokens` on empty responses. The `AI_FAILED` sentinel (`"ai failed"`) marks unrecoverable failures.

**C parsing** (`parsers/c/`): Three tree-sitter-based extractors:
- `globals.py` — walks declarations outside functions, distinguishes static/extern/definition
- `types.py` — regex-based extraction of typedefs/structs/unions/enums from `.h` files, with comment association
- `functions.py` — parses `.c` files for function definitions, resolves parameter types, pointer parameter directions (in/out/in out), global variable reads/writes (with direction), return types, and call relationships; builds `called_by` cross-references. Before parsing, `preprocess_c_code` collapses each `#if/#elif/#else` chain to **exactly one** surviving branch (tracking a per-level "chain taken" flag — an earlier bug kept every odd branch and leaked inactive variant `return`s into function analysis); `#ifdef`/`#ifndef` test user `defines` **plus names `#define`d in the file itself**; unknown identifiers in `#if` evaluate to 0 (C semantics, so `#if 0` drops); unresolvable expressions keep the first branch only. `find_return_statements` takes the statement's named child (not text replace) and dedupes distinct expressions in source order — bare `return;` yields nothing. Hardcoded call filter: `_IGNORED_CALLS = {"memcpy", "memset"}`. Each function also gets `conditional_macros` — the feature-flag names (`#ifdef`/`#ifndef`/`#if defined()`) that apply to it, attributed two ways by `_augment_functions_from_raw_source`: directives whose line falls inside the function's own raw-source range, **and** directives guarding a region that *encloses* the function (`_scan_conditional_regions`), so a file-wide `#ifdef … #endif` above the first function still lands on every function it wraps.

**Change detection** (`core/compare.py`): `compare_functions()` and `compare_types()` diff fresh extractions against cached data using `normalized_body` (whitespace-stripped) or structural type keys. Only changed items trigger AI re-runs. Supports rename detection by matching bodies/structures across added/removed sets.

**Config** (`config/`):
- `manager.py` — AI config stored per-platform in `swift-doc/config.json` (Windows: `%APPDATA%\swift-doc\`, macOS: `~/Library/Application Support/swift-doc/`, Linux: `~/.config/swift-doc/`). Required keys: `api_key`, `base_url`, `model_name`. Optional: `temperature` (default 1.0), `max_tokens` (default 800), `retry_count` (default 1). `STATE_DIR` is the config directory path. `APP_DIR_NAME = "swift-doc"`.
- `toml_config.py` — Project-level TOML config (`swift-doc.toml`). `load_toml(path)` parses a config file into a flat dict; `DEFAULT_CONFIG_TEMPLATE` is the documented template shipped in the Windows release artifact. `DEFAULT_CONFIG_NAME = "swift-doc.toml"` is the conventional config filename. AI config for `ai = "on"` comes from `manager.py` (per-user `config.json`); first run with `ai = "on"` triggers interactive onboarding via `ensure_ai_config_interactive()` — there is no separate config CLI command.

**Call-graph rendering** (`generators/images.py`): `style` TOML option:
- `"plain"` (default) — Pillow-rendered black/white, no shadows, sharp edges, thin lines
- `"table"` — embeds a two-column markdown/docx table (Callers | Callees) directly in the document. Self-calls are filtered out.

Long function names use `_wrap_text()` (underscore-aware line breaking) instead of truncation. Cards auto-size to fit wrapped text. Self-calls are stripped from callers/callees lists at render time.

**Data types** (`parsers/types.py`): TypedDict definitions for `GlobalVar`, `TypeDef`, `TypesData`, `FuncInput`, `FuncReturn`, `FuncDef` — these are the canonical shapes passed between parser, AI, compare, and generator modules.

## TOML Project Config (`swift-doc.toml`)

**Single usage:** `swift-doc <config.toml>` — the TOML config file is the only way to pass options; there are no CLI flags or subcommands. Entry logic in `cli.py:run_from_config()`. Resolution: **TOML > built-in defaults** (`cli.py:_DEFAULTS`), with per-option validation against `cli.py:_CHOICES` and a friendly error on bad values. `cli.py main()` rejects anything but exactly one `.toml` path argument.

Path semantics (drag-and-drop friendly): relative `root_dir`, `output_folder`, `cache_dir` resolve against the config file's directory; `analyse_dirs` entries resolve against `root_dir`. `verbose = true` in TOML enables debug logging.

Example:
```toml
root_dir = "examples/c"
format = "docx"
group_by = "file"
style = "plain"
ai = "off"

[ignore]
calls = ["memcpy", "memset"]
types = ["noisy_type"]
kinds = []
```

`DEFAULT_CONFIG_TEMPLATE` in `config/toml_config.py` is the canonical template; the Windows release workflow ships it as `swift-doc.toml` in the build artifact.

## Ignore Filtering

- `[ignore] calls` — filters function names from `calls` lists (not `called_by`). Applied at **docgen time** — cache stores complete data.
- `[ignore] types` — strips type names from `type_refs` and clears `type_ref` on global-variable inputs. Applied at **docgen time**.
- `[ignore] kinds` — drops types whose `kind` field matches. C kinds: struct, union, enum, typedef. Default: empty (no filtering). Applied at **docgen time**.
- Hardcoded baseline at extraction time: `_IGNORED_CALLS = {"memcpy", "memset"}` in `parsers/c/functions.py` — these are always filtered.

## Key Conventions

- Cache JSON files are named `{folder_name}_{global_variables|functions|global_types}.json` where `folder_name` is the basename of the project root.
- Function identity key is `(name, file)` tuple — allows static functions in different translation units to coexist.
- The `ai` TOML key accepts `"on"` or `"off"` (default: `"off"`).
- Encoding: files are decoded with chardet detection; `gb18030` is the fallback for Chinese-encoded source.
- `examples/c/` is a sample C project used for both manual testing and as a reference.
- ANSI color output is gated on `sys.stderr.isatty()` for piped/redirected usage.
- Group-by default: `file` (one doc per source file). Format default: `docx`.

## Development Conventions

**Every bug fix must include a regression test.** Add it to the appropriate file under `tests/`. Match the existing test class and method naming style (`TestCamelCase`, `test_snake_case`). Use inline C code strings via `parse_c_code()` for unit tests, temp files via `tmp_dir`/`tmp_path` fixtures for file-level tests.

**Keep CLAUDE.md current.** After any significant change — new feature, renamed component, changed default, fixed a tricky bug — update this file so the next agent has accurate context.

**Run the full suite before declaring done.** `pytest tests/ -q` must pass. If changing defaults, check that no existing test silently depends on the old default.

**Verify end-to-end for behavior changes.** Run `swift-doc examples/c/swift-doc.toml` (with `ai = "off"`) and inspect the output when touching extraction, generation, or filtering code. A passing unit test doesn't always catch a broken pipeline.

**Match existing patterns.** Follow the code style, naming, and structure already in the file you're editing. New test helpers mirror `parse_c_code()` / `find_first_function_node()` in `test_module_analysis.py`. New config keys follow the `OPTIONAL_CONFIG_JSON_MAP` pattern.

**Cache is source-of-truth.** Extraction produces complete, unfiltered data. Filtering (`[ignore] calls`, `[ignore] types`) happens at docgen time only. Never bake presentation concerns into the cache JSON.

**No backward-compatibility cruft.** Don't keep dual-mode APIs (file-path vs. in-memory) when only one mode has callers. If a parameter or code path is dead, delete it. Single-purpose, clean signatures over "might be useful later" flexibility.

**Use type annotations.** All new and modified Python code should include type annotations (PEP 484) on function signatures, method signatures, and module-level variables where the type isn't obvious. Use `from __future__ import annotations` when needed for forward references. Leverage standard library types (`list`, `dict`, `tuple`, `Optional`, `Union`) and TypedDict for structured data shapes already defined in `parsers/types.py`.

**tree-sitter node identity is unreliable.** `node is other` and `node == other` can both fail. Always compare `start_byte` positions.

## Communication Style

Speak warmly and naturally. Use affectionate words occasionally: dear, sweetie. Avoid repetition.
