import os
import json
import tempfile
import pytest

from pipeline import (
    build_analysis_paths,
    colorize_extract_phase_message,
    extract_global_variables,
    run_extract_phase,
    run_docgen_phase,
    EXTRACT_PHASE_START_COLOR,
    EXTRACT_PHASE_DONE_COLOR,
    COLOR_RESET,
)


class TestBuildAnalysisPaths:
    def test_directory_as_root(self, tmp_dir):
        paths = build_analysis_paths("/cache", tmp_dir)
        folder = os.path.basename(tmp_dir)
        assert paths["globals"].endswith(f"{folder}_global_variables.json")
        assert paths["types"].endswith(f"{folder}_global_types.json")
        assert paths["functions"].endswith(f"{folder}_functions.json")

    def test_file_as_root(self, tmp_dir):
        file_path = os.path.join(tmp_dir, "test.c")
        with open(file_path, "w") as f:
            f.write("// test")
        paths = build_analysis_paths("/cache", file_path)
        folder = os.path.basename(tmp_dir)
        assert paths["globals"].endswith(f"{folder}_global_variables.json")

    def test_all_keys_present(self, tmp_dir):
        paths = build_analysis_paths("/cache", tmp_dir)
        assert set(paths.keys()) == {"globals", "types", "functions"}

    def test_cache_dir_is_prepended(self, tmp_dir):
        paths = build_analysis_paths("/my_cache", tmp_dir)
        assert paths["globals"].startswith("/my_cache")


class TestColorizeExtractPhaseMessage:
    def test_adds_color_when_tty(self, monkeypatch):
        monkeypatch.setattr("sys.stderr.isatty", lambda: True)
        result = colorize_extract_phase_message("hello", EXTRACT_PHASE_START_COLOR)
        assert result.startswith(EXTRACT_PHASE_START_COLOR)
        assert result.endswith(COLOR_RESET)
        assert "hello" in result

    def test_no_color_when_not_tty(self, monkeypatch):
        monkeypatch.setattr("sys.stderr.isatty", lambda: False)
        result = colorize_extract_phase_message("hello", EXTRACT_PHASE_START_COLOR)
        assert result == "hello"
        assert COLOR_RESET not in result


class TestExtractGlobalVariables:
    def test_extracts_from_c_file(self, sample_c_file):
        output = os.path.join(os.path.dirname(sample_c_file), "globals_test.json")
        result = extract_global_variables(os.path.dirname(sample_c_file), output)
        assert os.path.exists(output)
        with open(output, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "globals" in data
        names = [g["name"] for g in data["globals"]]
        assert "counter" in names or "global_mode" in names

    def test_returns_output_path(self, sample_c_file):
        output = os.path.join(os.path.dirname(sample_c_file), "globals_test2.json")
        result = extract_global_variables(os.path.dirname(sample_c_file), output)
        assert result == output


class TestRunExtractPhase:
    def test_creates_cache_directory(self, sample_c_project, tmp_path):
        cache_dir = str(tmp_path / "extract_cache")
        import argparse

        args = argparse.Namespace(root_dir=sample_c_project, cache_dir=cache_dir, ai="oo", language="c")
        run_extract_phase(args)
        assert os.path.isdir(cache_dir)

    def test_creates_cache_files(self, sample_c_project, tmp_path):
        cache_dir = str(tmp_path / "extract_cache2")
        import argparse

        args = argparse.Namespace(root_dir=sample_c_project, cache_dir=cache_dir, ai="oo", language="c")
        run_extract_phase(args)
        folder = os.path.basename(os.path.normpath(sample_c_project))
        assert os.path.exists(os.path.join(cache_dir, f"{folder}_global_variables.json"))
        assert os.path.exists(os.path.join(cache_dir, f"{folder}_global_types.json"))
        assert os.path.exists(os.path.join(cache_dir, f"{folder}_functions.json"))


class TestRunDocgenPhase:
    def test_generates_markdown_and_figures(self, sample_c_project, tmp_path, sample_types_json, sample_globals_json):
        cache_dir = str(tmp_path / "docgen_cache")
        os.makedirs(cache_dir)

        folder = os.path.basename(os.path.normpath(sample_c_project))
        functions_path = os.path.join(cache_dir, f"{folder}_functions.json")

        # Create a minimal functions cache
        functions_data = {
            "functions": [
                {
                    "name": "add",
                    "file": os.path.join(sample_c_project, "sample.c"),
                    "inputs": [],
                    "returns": ["a + b"],
                    "body_code": "return a + b;",
                    "calls": [],
                    "called_by": [],
                    "algorithm_logic": "Adds two numbers.",
                }
            ]
        }
        with open(functions_path, "w", encoding="utf-8") as f:
            json.dump(functions_data, f)

        # Also create the types cache
        folder_name = os.path.basename(os.path.normpath(sample_c_project))
        types_cache_path = os.path.join(cache_dir, f"{folder_name}_global_types.json")
        with open(sample_types_json, "r", encoding="utf-8") as src:
            types_data = json.load(src)
        with open(types_cache_path, "w", encoding="utf-8") as f:
            json.dump(types_data, f)

        output_folder = str(tmp_path / "out_docs")

        import argparse

        args = argparse.Namespace(
            root_dir=sample_c_project,
            analyse_dirs=[sample_c_project],
            cache_dir=cache_dir,
            output_folder=output_folder,
        )
        run_docgen_phase(args)

        # Verify output
        assert os.path.isdir(os.path.join(output_folder, "figures"))
        assert os.path.exists(os.path.join(output_folder, "add.md"))
        assert os.path.exists(os.path.join(output_folder, "appendix.md"))

    def test_no_functions_under_analyse_dir(self, sample_c_project, tmp_path, sample_types_json):
        cache_dir = str(tmp_path / "docgen_cache2")
        os.makedirs(cache_dir)

        folder = os.path.basename(os.path.normpath(sample_c_project))
        functions_path = os.path.join(cache_dir, f"{folder}_functions.json")
        functions_data = {
            "functions": [
                {
                    "name": "add",
                    "file": "/other/project/sample.c",
                    "inputs": [],
                    "returns": [],
                    "body_code": "return 0;",
                    "calls": [],
                    "called_by": [],
                }
            ]
        }
        with open(functions_path, "w", encoding="utf-8") as f:
            json.dump(functions_data, f)

        types_cache_path = os.path.join(cache_dir, f"{os.path.basename(os.path.normpath(sample_c_project))}_global_types.json")
        with open(sample_types_json, "r", encoding="utf-8") as src:
            types_data = json.load(src)
        with open(types_cache_path, "w", encoding="utf-8") as f:
            json.dump(types_data, f)

        import argparse

        args = argparse.Namespace(
            root_dir=sample_c_project,
            analyse_dirs=["/other/project"],
            cache_dir=cache_dir,
            output_folder=str(tmp_path / "empty_out"),
        )
        run_docgen_phase(args)
        # Should not generate any files since functions don't match analyse_dir

    def test_missing_types_json_is_handled(self, sample_c_project, tmp_path):
        cache_dir = str(tmp_path / "docgen_cache3")
        os.makedirs(cache_dir)

        folder = os.path.basename(os.path.normpath(sample_c_project))
        functions_path = os.path.join(cache_dir, f"{folder}_functions.json")
        functions_data = {
            "functions": [
                {
                    "name": "simple",
                    "file": os.path.join(sample_c_project, "sample.c"),
                    "inputs": [],
                    "returns": [],
                    "body_code": "return 0;",
                    "calls": [],
                    "called_by": [],
                    "algorithm_logic": "Simple function.",
                }
            ]
        }
        with open(functions_path, "w", encoding="utf-8") as f:
            json.dump(functions_data, f)

        import argparse

        args = argparse.Namespace(
            root_dir=sample_c_project,
            analyse_dirs=[sample_c_project],
            cache_dir=cache_dir,
            output_folder=str(tmp_path / "out_docs3"),
        )
        run_docgen_phase(args)
        # Should not crash when types JSON is missing

    def test_missing_functions_json_is_handled(self, sample_c_project, tmp_path, sample_types_json):
        cache_dir = str(tmp_path / "docgen_cache4")
        os.makedirs(cache_dir)

        types_cache_path = os.path.join(
            cache_dir, f"{os.path.basename(os.path.normpath(sample_c_project))}_global_types.json"
        )
        with open(sample_types_json, "r", encoding="utf-8") as src:
            types_data = json.load(src)
        with open(types_cache_path, "w", encoding="utf-8") as f:
            json.dump(types_data, f)

        import argparse

        args = argparse.Namespace(
            root_dir=sample_c_project,
            analyse_dirs=[sample_c_project],
            cache_dir=cache_dir,
            output_folder=str(tmp_path / "out_docs4"),
        )
        run_docgen_phase(args)
        # Should not crash when functions JSON is missing
