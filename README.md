# swift-doc

C code analysis CLI that generates documentation with call graphs.

## Quick Start

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -e .

# Run on the built-in C example
swift-doc examples/c/swift-doc.toml
```

Output lands in the config's `output_folder` (default `out/` next to the config
file) — docs per file, call-graph PNGs in `figures/`, and a type appendix.

## Usage

There is exactly **one** way to run swift-doc — give it a TOML config file:

```bash
swift-doc <config.toml>
```

On Windows you can also drag a `swift-doc.toml` onto `swift-doc.exe`.
There are no CLI flags; every option lives in the config file. Relative paths
(`root_dir`, `output_folder`, `cache_dir`) resolve against the config file's
directory, and `analyse_dirs` entries resolve against `root_dir`.

A template config is available in the release bundle (`swift-doc.toml`) and at
[`examples/c/swift-doc.toml`](examples/c/swift-doc.toml).

## Project Configuration (`swift-doc.toml`)

| Key | Default | Description |
|---|---|---|
| `root_dir` | *required* | Project root to analyze |
| `analyse_dirs` | `[root_dir]` | Subset of directories/files to generate docs for |
| `cache_dir` | platform cache | Intermediate JSON directory |
| `output_folder` | `out` | Output directory for docs and figures |
| `ai` | `off` | `on` / `off` for AI-generated descriptions |
| `ai_workers` | `6` | Number of parallel AI workers for enrichment |
| `format` | `docx` | Output format (`markdown`, `docx`) |
| `group_by` | `file` | Group docs per `function` or per `file` |
| `style` | `plain` | Call-graph style (`plain`/`slate`/`fearless`/`red` images, or `table` inline) |
| `embedded_global_reference` | `no` | Embed renumbered type references (A_1, A_2, …) in each document |
| `out_param_location` | `inputs` | Place out-only pointer params under inputs or outputs |
| `verbose` | `false` | Enable debug logging |
| `[ignore] calls` | `[]` | Function names to exclude from call graphs |
| `[ignore] types` | `[]` | Type names to exclude from extraction |
| `[ignore] kinds` | `[]` | Type kinds to exclude: struct, union, enum, typedef |
| `[define] macros` | `[]` | Preprocessor macros to mark as defined |
| `[sections] *` | all `true` | Set any section key to `false` to skip it in generated docs |

Example:

```toml
root_dir = "my-project"

# Output options
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

## AI Configuration

AI-powered descriptions are used when `ai = "on"`. The first run prompts you
through an interactive onboarding (API key, base URL, model name); settings
are then stored per-user and can be edited directly in that file:

| OS | Path |
|---|---|
| Linux | `~/.config/swift-doc/config.json` |
| macOS | `~/Library/Application Support/swift-doc/config.json` |
| Windows | `%APPDATA%\swift-doc\config.json` |

Keys: `api_key`, `base_url`, `model_name` (required); `temperature` (1.0),
`max_tokens` (800), `retry_count` (1) (optional).

## Windows Release

The `Build Windows release` GitHub workflow produces an artifact containing:

- `swift-doc.exe` — the single-file executable
- `README.md`
- `swift-doc.toml` — the template project config

Build the exe locally with:

```bash
pip install pyinstaller
pyinstaller --name swift-doc --onefile --clean --paths src src/cli.py
# dist/swift-doc.exe
```

## Running Tests

```bash
pytest tests/ -v
pytest tests/test_module_analysis.py -v
pytest tests/test_module_analysis.py::TestAnalyzePointerDirections -v
```
