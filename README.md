# aoto_md

## CLI Usage

```bash
python src/cli.py root_dir [--analyse_dir ANALYSE_DIR] [--cache_dir CACHE_DIR] [--output_folder OUTPUT_FOLDER] [--ai {on,off}]
```

### Positional Argument

- `root_dir` (required): module directory or a single `.c` file for documentation generation.

### Optional Arguments

- `--analyse_dir`: analysis scope under `root_dir` for extract phase. If omitted, defaults to `root_dir`.
- `--cache_dir`: cache directory for intermediate JSON files. Default: `.analysis`.
- `--output_folder`: output directory for markdown and figures. Default: `out`.
- `--ai`: AI mode for doc generation updates. Choices: `on` or `off`. Default: `on`.

## Examples

```bash
# Use root_dir for both extraction and doc generation
python src/cli.py ATP_CODE/INIT
```

```bash
# Analyse a subdirectory inside root_dir
python src/cli.py ATP_CODE --analyse_dir ATP_CODE/INIT
```

```bash
# Disable AI updates during doc generation
python src/cli.py ATP_CODE/INIT --ai off
```

```bash
# Custom cache and output directories
python src/cli.py ATP_CODE/INIT --cache_dir .analysis --output_folder MD
```
