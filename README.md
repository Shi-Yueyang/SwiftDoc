# aoto_md

## CLI Usage

```bash
python src/cli.py generate root_dir [--analyse_dir ANALYSE_DIR] [--cache_dir CACHE_DIR] [--output_folder OUTPUT_FOLDER] [--ai {on,off}]
python src/cli.py config
```

Legacy generate form is still supported:

```bash
python src/cli.py root_dir [--analyse_dir ANALYSE_DIR] [--cache_dir CACHE_DIR] [--output_folder OUTPUT_FOLDER] [--ai {on,off}]
```

## Commands

- `generate`: extract project data and generate markdown documentation.
- `config`: rerun the interactive AI onboarding flow and rewrite the user config if needed.

## AI Configuration

When `generate --ai on` is used, the CLI reads AI settings only from the per-user JSON config file.

If AI is enabled and the config file is missing or incomplete, the CLI starts an interactive onboarding flow. It prompts for the missing values, tests the connection before saving, and only writes the config file after the test succeeds.

Running `python src/cli.py config` always reruns onboarding, even if a complete config file already exists.

When `generate --ai off` is used, onboarding is skipped entirely and extract/docgen runs without AI-generated descriptions.

### User Config Location

- Linux: `${XDG_CONFIG_HOME:-~/.config}/aoto-md/config.json`
- macOS: `~/Library/Application Support/aoto-md/config.json`
- Windows: `%APPDATA%\\aoto-md\\config.json`

### Notes

- `.env` and process environment variables are not used for AI configuration.
- Secrets are not accepted through CLI arguments.
- Interrupting onboarding with `Ctrl+C` exits cleanly without saving.

### Positional Argument

- `root_dir` (required): project root directory used for the extract phase.

### Optional Arguments

- `--analyse_dir`: subset of `root_dir` used for documentation generation. It can be a module directory or a single `.c` file. If omitted, defaults to `root_dir`.
- `--cache_dir`: cache directory for intermediate JSON files. Default: `.analysis`.
- `--output_folder`: output directory for markdown and figures. Default: `out`.
- `--ai`: AI mode for type and function analysis. When `on`, missing config triggers interactive onboarding. Default: `off`.

## Examples

```bash
python src/cli.py generate ATP_CODE
python src/cli.py generate ATP_CODE --analyse_dir ATP_CODE/DMI
python src/cli.py generate ATP_CODE/MT --analyse_dir ATP_CODE/MT --cache_dir .analysis --output_folder out --ai on
python src/cli.py config
```

The CLI now works in two stages:

- Extract scans `root_dir` to build the shared cache.
- Doc generation filters that extracted data down to `analyse_dir`.
- `analyse_dir` must stay inside `root_dir`.

## Build Executable

Build from the repository root with PyInstaller:

```bash
./.venv/bin/pip install pyinstaller
./.venv/bin/pyinstaller --name aoto-md --onedir --clean --paths src src/cli.py
```

The executable will be created under `dist/aoto-md/`.

Run it on Linux with:

```bash
./dist/aoto-md/cli generate ATP_CODE --analyse_dir ATP_CODE/DMI
```

If you want a single-file executable instead of a directory build:

```bash
./.venv/bin/pyinstaller --name aoto-md --onefile --clean --paths src src/cli.py
```

Notes:

- Start with `--onedir` first. It is usually easier to debug with `matplotlib`, `tree-sitter`, and `tree-sitter-c`.
- The executable still reads AI config from the per-user config file, not from the repository.
- On this machine, the documented build command did not run until the Python shared library for the active interpreter was available.
- If the bundled app misses package data, try:

```bash
./.venv/bin/pyinstaller --name aoto-md --onedir --clean --paths src --collect-all matplotlib src/cli.py
```
