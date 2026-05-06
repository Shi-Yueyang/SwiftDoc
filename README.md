# aoto_md

## Quick Start

```bash
pip install -r requirements.txt
python src/main.py ATP_CODE/INIT --cache-dir .analysis --output_folder MD --output_format md --ai off
```

## Re-run

```bash
python src/main.py ATP_CODE/INIT --cache-dir .analysis --output_folder MD --output_format md --ai off
```

## Run with AI

```bash
python src/main.py ATP_CODE/INIT --cache-dir .analysis --output_folder MD --output_format md --ai on
```

## Environment Setup Examples

```bash
# venv
python3 -m venv .venv
source .venv/bin/activate
```

```bash
# conda
conda create -n aoto_md python=3.11 -y
conda activate aoto_md
```

```bash
# pipenv
pipenv --python 3.11
pipenv shell
```
