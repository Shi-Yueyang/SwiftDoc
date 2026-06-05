# swift-doc

Multi-language code analysis CLI that generates documentation with call graphs.

## Quick Start

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -e .

# Run on the built-in C example
swift-doc generate examples/c --ai off

# Run on the Ada example
swift-doc generate examples/ada --lang ada --ai off
```

Output lands in `out/` by default — docs per file, call-graph PNGs in `out/figures/`, and a type appendix.

## Commands

### `generate` — analyze source and produce docs

```bash
# Project directory (auto-discovers swift-doc.toml inside)
swift-doc generate examples/c

# Explicit TOML config file
swift-doc generate my-config.toml

# CLI-only (no config needed)
swift-doc generate examples/c --lang c --format markdown --group-by function

# Scope to specific directories or files
swift-doc generate examples/c --analyse_dir examples/c/bsw --analyse_dir examples/c/drivers

# Filter noisy calls from call graphs
swift-doc generate examples/c --ignore-calls free --ignore-calls malloc

# With AI-powered descriptions (requires config)
swift-doc generate examples/c --ai on
```

| Argument | Default | Description |
|---|---|---|
| `root_dir` | auto-discovered | Project root or path to a `.toml` config file |
| `--lang` | `auto` | Source language (`c`, `ada`, or `auto`) |
| `--analyse_dir` | root_dir | Subset to generate docs for (repeatable) |
| `--cache_dir` | platform cache | Intermediate JSON directory |
| `--output_folder` | `out` | Output directory for docs and figures |
| `--ai` | `off` | `on` / `off` for AI-generated descriptions |
| `--format` | `docx` | Output format (`markdown`, `docx`) |
| `--group-by` | `file` | Group docs per `function` or per `file` |
| `--style` | `plain` | Call-graph style (`plain` black/white, `modern` colorful, or `table` inline) |
| `--ignore-kinds` | — | Type kinds to exclude: typedef, enum, struct, union (repeatable) |
| `--ignore-calls` | — | Function names to exclude from call graphs (repeatable) |
| `--ignore-types` | — | Type names to exclude from extraction (repeatable) |
| `--verbose` | off | Enable debug logging |

### `config` — manage AI settings

```bash
swift-doc config                    # interactive onboarding
swift-doc config temperature 0.7   # set single value
swift-doc config max_tokens 1500
swift-doc config retry_count 3
```

Settings are stored per-user:

| OS | Path |
|---|---|
| Linux | `~/.config/swift-doc/config.json` |
| macOS | `~/Library/Application Support/swift-doc/config.json` |
| Windows | `%APPDATA%\swift-doc\config.json` |

### `clear-cache` — remove cached analysis data

```bash
swift-doc clear-cache                     # clears the last-used cache dir
swift-doc clear-cache --cache_dir .analysis  # clears a specific cache dir
swift-doc clear                           # alias for clear-cache
```

## Project Configuration (`swift-doc.toml`)

Place a `swift-doc.toml` in your project root to avoid typing CLI flags every time.
The tool auto-discovers it when you run `swift-doc generate <project-dir>`.

```toml
root_dir = "my-project"

# Output options
lang = "c"
output_folder = "out"
format = "docx"
group_by = "file"
style = "plain"

# Extraction options
ai = "off"
# cache_dir = ".analysis"
# analyse_dirs = ["my-project/sub", "my-project/other"]

# Ignore lists
[ignore]
calls = ["memcpy", "memset", "free"]
types = ["noisy_type"]
kinds = []
```

CLI flags always override TOML values. See `examples/c/swift-doc.toml` for a worked example.

## Build Executable

```bash
pip install pyinstaller
pyinstaller --name swift-doc --onefile --clean --paths src src/cli.py
# dist/swift-doc  (or dist/swift-doc.exe on Windows)
```

## Project Structure

```
src/
├── cli.py                        # entry point
├── pipeline.py                   # two-phase orchestrator
├── config/
│   ├── manager.py                # AI config (config.json)
│   └── toml_config.py            # project config (swift-doc.toml)
├── core/                         # shared utils, AI client, diff engine
├── parsers/
│   ├── base.py                   # BaseParser ABC
│   ├── c/                        # C parser (tree-sitter)
│   └── ada/                      # Ada parser (tree-sitter)
├── generators/
│   ├── markdown/                 # markdown output
│   ├── docx/                     # docx output
│   └── images.py                 # call-graph renderer (matplotlib)

examples/
├── c/                            # sample C project
└── ada/                          # sample Ada project
```

## Running Tests

```bash
pytest tests/ -v
pytest tests/test_module_analysis.py -v
pytest tests/test_module_analysis.py::TestAnalyzePointerDirections -v
```
