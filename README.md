# auto-md

Multi-language code analysis CLI that generates documentation with call graphs.

## Quick Start

```bash
# Setup
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e .

# Run on the built-in C example (no AI needed)
python -m cli generate c examples/c --ai off

# Open the generated docs
#   out/          — markdown files per function
#   out/figures/  — call-graph PNGs
#   out/appendix.md — type definitions
```

## Commands

### `generate` — full analysis + docs

```bash
# Entire project
python -m cli generate c examples/c --ai off

# Specific subdirectories or files
python -m cli generate c examples/c --analyse_dir examples/c/bsw --analyse_dir examples/c/drivers

# Single file
python -m cli generate c examples/c --analyse_dir examples/c/comm/sensor.c --ai off

# With custom cache/output paths
python -m cli generate c examples/c --cache_dir .analysis --output_folder out_docs --ai on
```

| Argument | Default | Description |
|---|---|---|
| `lang` | *(required)* | Source language (e.g. `c`) |
| `root_dir` | *(required)* | Project root for the extract phase |
| `--analyse_dir` | root_dir | Subset to generate docs for (repeatable) |
| `--cache_dir` | platform cache | Intermediate JSON directory |
| `--output_folder` | `out` | Output directory for docs and figures |
| `--ai` | `oo` | `on` / `off` for AI-generated descriptions |
| `--format` | `markdown` | Output documentation format |
| `--verbose` | off | Enable debug logging |

### `config` — manage AI settings

```bash
python -m cli config                          # interactive onboarding
python -m cli config temperature 0.7          # set single value
python -m cli config max_tokens 1500
python -m cli config retry_count 3
```

Settings are stored per-user:

| OS | Path |
|---|---|
| Linux | `~/.config/aoto-md/config.json` |
| macOS | `~/Library/Application Support/aoto-md/config.json` |
| Windows | `%APPDATA%\aoto-md\config.json` |

## Build Executable

```bash
pip install pyinstaller
pyinstaller --name auto-md --onefile --clean --paths src src/cli.py
# dist/auto-md.exe  (or dist/auto-md on Linux/macOS)
```

## Project Structure

```
src/
├── cli.py                     # entry point
├── pipeline.py                # orchestrator
├── config/manager.py          # AI settings
├── core/                      # shared utils, AI, compare
├── parsers/
│   ├── base.py                # BaseParser ABC — subclass to add a language
│   └── c/                     # C language parser
├── generators/
│   ├── markdown/              # markdown doc generator
│   └── images.py              # call-graph generator

examples/
└── c/                         # sample C project for testing
```
