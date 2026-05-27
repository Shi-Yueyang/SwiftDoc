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
        assert paths["globals"].endswith("_global_variables.json")
        assert paths["types"].endswith("_global_types.json")
        assert paths["functions"].endswith("_functions.json")

    def test_file_as_root(self, tmp_dir):
        file_path = os.path.join(tmp_dir, "test.c")
        with open(file_path, "w") as f:
            f.write("// test")
        paths = build_analysis_paths("/cache", file_path)
        assert paths["globals"].endswith("_global_variables.json")

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

        args = argparse.Namespace(root_dir=sample_c_project, cache_dir=cache_dir, ai="off", language="c")
        run_extract_phase(args)
        assert os.path.isdir(cache_dir)

    def test_creates_cache_files(self, sample_c_project, tmp_path):
        cache_dir = str(tmp_path / "extract_cache2")
        import argparse

        args = argparse.Namespace(root_dir=sample_c_project, cache_dir=cache_dir, ai="off", language="c")
        run_extract_phase(args)
        paths = build_analysis_paths(cache_dir, sample_c_project)
        assert os.path.exists(paths["globals"])
        assert os.path.exists(paths["types"])
        assert os.path.exists(paths["functions"])


class TestRunDocgenPhase:
    def test_generates_markdown_and_figures(self, sample_c_project, tmp_path, sample_types_json, sample_globals_json):
        cache_dir = str(tmp_path / "docgen_cache")
        os.makedirs(cache_dir)

        paths = build_analysis_paths(cache_dir, sample_c_project)
        functions_path = paths["functions"]

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
        types_cache_path = paths["types"]
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

        paths = build_analysis_paths(cache_dir, sample_c_project)
        functions_path = paths["functions"]
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

        types_cache_path = paths["types"]
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

        paths = build_analysis_paths(cache_dir, sample_c_project)
        functions_path = paths["functions"]
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

class TestIntegrationC:
    """End-to-end pipeline tests against the built-in C example project."""

    @pytest.fixture
    def c_example_dir(self):
        import pathlib
        return str(pathlib.Path(__file__).resolve().parent.parent / "examples" / "c")

    def test_full_pipeline_generates_expected_output(self, c_example_dir, tmp_path):
        import argparse
        cache_dir = str(tmp_path / "cache")
        out_dir = str(tmp_path / "out")

        # Extract phase
        extract_args = argparse.Namespace(
            root_dir=c_example_dir, cache_dir=cache_dir, ai="off", language="c",
        )
        run_extract_phase(extract_args)

        # Verify cache files
        paths = build_analysis_paths(cache_dir, c_example_dir)
        assert os.path.exists(paths["globals"])
        assert os.path.exists(paths["types"])
        assert os.path.exists(paths["functions"])

        # Verify cache content
        with open(paths["functions"]) as f:
            funcs_data = json.load(f)
        funcs = funcs_data["functions"]
        func_names = {f["name"] for f in funcs}
        assert "main" in func_names
        assert all("name" in f and "file" in f and "calls" in f for f in funcs)

        with open(paths["types"]) as f:
            types_data = json.load(f)
        type_defs = types_data["type_definitions"]
        assert "Point" in type_defs or "Direction" in type_defs or "Status" in type_defs

        # Docgen phase
        docgen_args = argparse.Namespace(
            root_dir=c_example_dir, analyse_dirs=[c_example_dir],
            cache_dir=cache_dir, output_folder=out_dir,
            format="markdown", group_by="function",
        )
        run_docgen_phase(docgen_args)

        # Verify markdown output
        assert os.path.isdir(os.path.join(out_dir, "figures"))
        assert os.path.exists(os.path.join(out_dir, "main.md"))
        assert os.path.exists(os.path.join(out_dir, "appendix.md"))

        # Verify appendix contains C syntax, not Ada
        with open(os.path.join(out_dir, "appendix.md")) as f:
            appendix = f.read()
        assert "typedef struct" in appendix or "typedef enum" in appendix or "typedef" in appendix

        # Verify function doc has expected headings
        with open(os.path.join(out_dir, "main.md")) as f:
            md = f.read()
        assert "function：main" in md
        assert "输入项" in md

    def test_per_file_grouping(self, c_example_dir, tmp_path):
        import argparse
        cache_dir = str(tmp_path / "cache")
        out_dir = str(tmp_path / "out")

        extract_args = argparse.Namespace(
            root_dir=c_example_dir, cache_dir=cache_dir, ai="off", language="c",
        )
        run_extract_phase(extract_args)

        docgen_args = argparse.Namespace(
            root_dir=c_example_dir, analyse_dirs=[c_example_dir],
            cache_dir=cache_dir, output_folder=out_dir,
            format="markdown", group_by="file",
        )
        run_docgen_phase(docgen_args)

        # Should have per-file output with correct extension
        assert os.path.exists(os.path.join(out_dir, "main.md"))
        with open(os.path.join(out_dir, "main.md")) as f:
            first_line = f.readline().strip()
        assert first_line == "# main.c"


class TestIntegrationAda:
    """End-to-end pipeline tests against the built-in Ada example project."""

    @pytest.fixture
    def ada_example_dir(self):
        import pathlib
        return str(pathlib.Path(__file__).resolve().parent.parent / "examples" / "ada")

    def test_full_pipeline_generates_expected_output(self, ada_example_dir, tmp_path):
        import argparse
        cache_dir = str(tmp_path / "cache")
        out_dir = str(tmp_path / "out")

        # Extract phase
        extract_args = argparse.Namespace(
            root_dir=ada_example_dir, cache_dir=cache_dir, ai="off", language="ada",
        )
        run_extract_phase(extract_args)

        # Verify cache files
        paths = build_analysis_paths(cache_dir, ada_example_dir)
        assert os.path.exists(paths["globals"])
        assert os.path.exists(paths["types"])
        assert os.path.exists(paths["functions"])

        # Verify function cache
        with open(paths["functions"]) as f:
            funcs_data = json.load(f)
        funcs = funcs_data["functions"]
        func_names = {f["name"] for f in funcs}
        assert "Main" in func_names
        assert "Read_Sensor" in func_names
        # Verify call graph is populated
        main = next(f for f in funcs if f["name"] == "Main")
        assert len(main["calls"]) > 0

        # Verify type cache has Ada types
        with open(paths["types"]) as f:
            types_data = json.load(f)
        type_defs = types_data["type_definitions"]
        assert "Status" in type_defs
        assert "Point" in type_defs

        # Docgen phase
        docgen_args = argparse.Namespace(
            root_dir=ada_example_dir, analyse_dirs=[ada_example_dir],
            cache_dir=cache_dir, output_folder=out_dir,
            format="markdown", group_by="function",
            language="ada",
        )
        run_docgen_phase(docgen_args)

        # Verify markdown output
        assert os.path.isdir(os.path.join(out_dir, "figures"))
        assert os.path.exists(os.path.join(out_dir, "Main.md"))
        assert os.path.exists(os.path.join(out_dir, "appendix.md"))

        # Verify appendix has Ada syntax, not C
        with open(os.path.join(out_dir, "appendix.md")) as f:
            appendix = f.read()
        assert "end record" in appendix or "type" in appendix
        assert "typedef struct" not in appendix

    def test_per_file_grouping_uses_adb_extension(self, ada_example_dir, tmp_path):
        import argparse
        cache_dir = str(tmp_path / "cache")
        out_dir = str(tmp_path / "out")

        extract_args = argparse.Namespace(
            root_dir=ada_example_dir, cache_dir=cache_dir, ai="off", language="ada",
        )
        run_extract_phase(extract_args)

        docgen_args = argparse.Namespace(
            root_dir=ada_example_dir, analyse_dirs=[ada_example_dir],
            cache_dir=cache_dir, output_folder=out_dir,
            format="markdown", group_by="file",
            language="ada",
        )
        run_docgen_phase(docgen_args)

        # Heading should use .adb not .c
        assert os.path.exists(os.path.join(out_dir, "main.md"))
        with open(os.path.join(out_dir, "main.md")) as f:
            first_line = f.readline().strip()
        assert first_line == "# main.adb"

    def test_direction_modes_in_output(self, ada_example_dir, tmp_path):
        import argparse
        cache_dir = str(tmp_path / "cache")
        out_dir = str(tmp_path / "out")

        extract_args = argparse.Namespace(
            root_dir=ada_example_dir, cache_dir=cache_dir, ai="off", language="ada",
        )
        run_extract_phase(extract_args)

        docgen_args = argparse.Namespace(
            root_dir=ada_example_dir, analyse_dirs=[ada_example_dir],
            cache_dir=cache_dir, output_folder=out_dir,
            format="markdown", group_by="function",
            language="ada",
        )
        run_docgen_phase(docgen_args)

        # Init_Spi has an 'out' parameter and a global var
        with open(os.path.join(out_dir, "Init_Spi.md")) as f:
            md = f.read()
        assert "out" in md  # direction mode


class TestRunDocgenPhaseMissingFunctions:
    def test_missing_functions_json_is_handled(self, sample_c_project, tmp_path, sample_types_json):
        cache_dir = str(tmp_path / "docgen_cache4")
        os.makedirs(cache_dir)

        paths = build_analysis_paths(cache_dir, sample_c_project)
        types_cache_path = paths["types"]
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
