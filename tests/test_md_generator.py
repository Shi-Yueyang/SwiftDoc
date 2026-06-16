import os
import json
import pytest

from generators.common import (
    normalize_function_for_doc,
    remove_c_comments,
    generate_definition,
)
from generators.markdown.functions import (
    generate_function_md,
    generate_function_md_by_file,
    _write_function_section,
)
from generators.markdown.appendix import generate_appendix_md


class TestNormalizeFunctionForDoc:
    def test_sets_default_start_line(self):
        result = normalize_function_for_doc({"name": "foo"})
        assert result["start_line"] == 0

    def test_preserves_existing_start_line(self):
        result = normalize_function_for_doc({"name": "foo", "start_line": 42})
        assert result["start_line"] == 42

    def test_sets_default_conditional_macros(self):
        result = normalize_function_for_doc({"name": "foo"})
        assert result["conditional_macros"] == []

    def test_preserves_existing_conditional_macros(self):
        result = normalize_function_for_doc({"name": "foo", "conditional_macros": ["A", "B"]})
        assert result["conditional_macros"] == ["A", "B"]

    def test_sets_default_algorithm_logic(self):
        result = normalize_function_for_doc({"name": "foo"})
        assert result["algorithm_logic"] == ""

    def test_preserves_existing_algorithm_logic(self):
        result = normalize_function_for_doc({"name": "foo", "algorithm_logic": "Does something."})
        assert result["algorithm_logic"] == "Does something."

    def test_normalizes_inputs(self):
        result = normalize_function_for_doc({
            "name": "foo",
            "inputs": [{"name": "a", "type": "int"}],
        })
        assert result["inputs"][0]["inputs_description"] == ""

    def test_converts_string_returns_to_dicts(self):
        result = normalize_function_for_doc({
            "name": "foo",
            "returns": ["a + b"],
        })
        assert result["returns"] == [{"expression": "a + b", "return_description": ""}]

    def test_normalizes_empty_returns(self):
        result = normalize_function_for_doc({
            "name": "foo",
            "returns": [],
        })
        assert result["returns"] == []

    def test_handles_returns_not_list(self):
        result = normalize_function_for_doc({
            "name": "foo",
        })
        assert result["returns"] == []


class TestRemoveCComments:
    def test_removes_block_comment(self):
        result = remove_c_comments("int x; /* comment */ int y;")
        assert "comment" not in result
        assert "int x;" in result
        assert "int y;" in result

    def test_removes_line_comment(self):
        result = remove_c_comments("int x; // comment\nint y;")
        assert "comment" not in result
        assert "int x;" in result
        assert "int y;" in result

    def test_preserves_code_outside_comments(self):
        result = remove_c_comments("int x = 5; /* inline */ return x;")
        assert "int x = 5;" in result
        assert "return x;" in result


class TestGenerateDefinition:
    def test_struct_definition(self):
        info = {"kind": "struct", "members": ["int x", "int y"]}
        result = generate_definition("Point", info)
        assert "Point" in result
        assert "typedef struct" in result
        assert "int x" in result
        assert "int y" in result

    def test_struct_no_members(self):
        info = {"kind": "struct", "members": []}
        result = generate_definition("Empty", info)
        assert "typedef struct" in result
        assert "Empty" in result

    def test_union_definition(self):
        info = {"kind": "union", "members": ["int x", "float y"]}
        result = generate_definition("Data", info)
        assert "typedef union" in result
        assert "Data" in result

    def test_enum_definition(self):
        info = {"kind": "enum", "values": ["A", "B", "C"]}
        result = generate_definition("Color", info)
        assert "typedef enum" in result
        assert "A" in result
        assert "B" in result

    def test_enum_no_values(self):
        info = {"kind": "enum", "values": []}
        result = generate_definition("Color", info)
        assert "typedef enum" in result
        assert "no values" in result

    def test_typedef_definition(self):
        info = {"kind": "typedef", "original_type": "unsigned char"}
        result = generate_definition("BYTE", info)
        assert "unsigned char" in result
        assert "BYTE" in result

    def test_unknown_kind(self):
        info = {"kind": "weird", "original_type": "int"}
        result = generate_definition("X", info)
        assert "X" in result
        assert "unknown kind" in result


class TestGenerateFunctionMd:
    def test_generates_md_files(self, sample_functions, sample_types_json, tmp_path):
        output_dir = str(tmp_path / "md_output")
        figures_dir = str(tmp_path / "figures")
        os.makedirs(figures_dir)
        # Create dummy figure images
        for func in sample_functions:
            img_path = os.path.join(figures_dir, f"{func['name']}.png")
            with open(img_path, "w") as f:
                f.write("dummy")

        generate_function_md(
            function_list=sample_functions,
            types_json=sample_types_json,
            figures_dir=figures_dir,
            output_dir=output_dir,
        )

        for func in sample_functions:
            md_path = os.path.join(output_dir, f"{func['name']}.md")
            assert os.path.exists(md_path)
            content = open(md_path, "r", encoding="utf-8").read()
            assert func["name"] in content

    def test_generates_input_table(self, sample_functions, sample_types_json, tmp_path):
        output_dir = str(tmp_path / "md_output2")
        figures_dir = str(tmp_path / "figures2")
        os.makedirs(figures_dir)
        for func in sample_functions:
            img_path = os.path.join(figures_dir, f"{func['name']}.png")
            with open(img_path, "w") as f:
                f.write("dummy")

        generate_function_md(
            function_list=sample_functions,
            types_json=sample_types_json,
            figures_dir=figures_dir,
            output_dir=output_dir,
        )

        main_md = open(os.path.join(output_dir, "main.md"), "r", encoding="utf-8").read()
        assert "输入项" in main_md
        assert "argc" in main_md
        assert "argv" in main_md
        assert "global_mode" in main_md

    def test_generates_output_table(self, sample_functions, sample_types_json, tmp_path):
        output_dir = str(tmp_path / "md_output3")
        figures_dir = str(tmp_path / "figures3")
        os.makedirs(figures_dir)
        for func in sample_functions:
            img_path = os.path.join(figures_dir, f"{func['name']}.png")
            with open(img_path, "w") as f:
                f.write("dummy")

        generate_function_md(
            function_list=sample_functions,
            types_json=sample_types_json,
            figures_dir=figures_dir,
            output_dir=output_dir,
        )

        main_md = open(os.path.join(output_dir, "main.md"), "r", encoding="utf-8").read()
        assert "输出项" in main_md

    def test_generates_algorithm_section(self, sample_functions, sample_types_json, tmp_path):
        output_dir = str(tmp_path / "md_output4")
        figures_dir = str(tmp_path / "figures4")
        os.makedirs(figures_dir)
        for func in sample_functions:
            img_path = os.path.join(figures_dir, f"{func['name']}.png")
            with open(img_path, "w") as f:
                f.write("dummy")

        generate_function_md(
            function_list=sample_functions,
            types_json=sample_types_json,
            figures_dir=figures_dir,
            output_dir=output_dir,
        )

        main_md = open(os.path.join(output_dir, "main.md"), "r", encoding="utf-8").read()
        assert "Entry point" in main_md

    def test_includes_module_description_section(self, sample_functions, sample_types_json, tmp_path):
        output_dir = str(tmp_path / "md_output_mod_desc")
        figures_dir = str(tmp_path / "figures_mod_desc")
        os.makedirs(figures_dir)
        for func in sample_functions:
            img_path = os.path.join(figures_dir, f"{func['name']}.png")
            with open(img_path, "w") as f:
                f.write("dummy")

        generate_function_md(
            function_list=sample_functions,
            types_json=sample_types_json,
            figures_dir=figures_dir,
            output_dir=output_dir,
        )

        main_md = open(os.path.join(output_dir, "main.md"), "r", encoding="utf-8").read()
        assert "### 模块描述" in main_md
        assert "**函数名 Function name:** main" in main_md
        assert "**文件名 File name:** /project/main.c" in main_md
        assert "**行号 Line number:** 10" in main_md
        assert "**宏列表 Macro list:**" in main_md
        assert "- FEATURE_X" in main_md
        assert "- USE_LOG" in main_md

    # Test with figure reference
    def test_includes_figure_reference(self, sample_functions, sample_types_json, tmp_path):
        output_dir = str(tmp_path / "md_output5")
        figures_dir = str(tmp_path / "figures5")
        os.makedirs(figures_dir)
        for func in sample_functions:
            img_path = os.path.join(figures_dir, f"{func['name']}.png")
            with open(img_path, "w") as f:
                f.write("dummy")

        generate_function_md(
            function_list=sample_functions,
            types_json=sample_types_json,
            figures_dir=figures_dir,
            output_dir=output_dir,
        )

        main_md = open(os.path.join(output_dir, "main.md"), "r", encoding="utf-8").read()
        assert "main.png" in main_md or "接口" in main_md

    # Edge: empty input/return
    def test_empty_inputs_and_returns(self, sample_types_json, tmp_path):
        output_dir = str(tmp_path / "md_output_empty")
        figures_dir = str(tmp_path / "figures_empty")
        os.makedirs(figures_dir)
        funcs = [{
            "name": "empty_func",
            "file": "/proj/empty.c",
            "inputs": [],
            "returns": [],
            "body_code": "",
            "calls": [],
            "called_by": [],
            "algorithm_logic": "Does nothing.",
        }]
        img_path = os.path.join(figures_dir, "empty_func.png")
        with open(img_path, "w") as f:
            f.write("dummy")

        generate_function_md(
            function_list=funcs,
            types_json=sample_types_json,
            figures_dir=figures_dir,
            output_dir=output_dir,
        )

        content = open(os.path.join(output_dir, "empty_func.md"), "r", encoding="utf-8").read()
        assert "N/A" in content


class TestGroupByFile:
    def test_generates_one_md_per_source_file(self, sample_functions, sample_types_json, tmp_path):
        output_dir = str(tmp_path / "md_by_file")
        figures_dir = str(tmp_path / "figures_by_file")
        os.makedirs(figures_dir)
        for func in sample_functions:
            with open(os.path.join(figures_dir, f"{func['name']}.png"), "w") as f:
                f.write("dummy")

        generate_function_md_by_file(sample_functions, sample_types_json, figures_dir, output_dir)

        # Should produce one .md per unique file
        files = {func["file"] for func in sample_functions}
        for file_path in files:
            base = os.path.splitext(os.path.basename(file_path))[0]
            md_path = os.path.join(output_dir, f"{base}.md")
            assert os.path.exists(md_path), f"Missing {base}.md"

    def test_file_md_contains_all_functions(self, sample_functions, sample_types_json, tmp_path):
        output_dir = str(tmp_path / "md_by_file2")
        figures_dir = str(tmp_path / "figures_by_file2")
        os.makedirs(figures_dir)
        for func in sample_functions:
            with open(os.path.join(figures_dir, f"{func['name']}.png"), "w") as f:
                f.write("dummy")

        generate_function_md_by_file(sample_functions, sample_types_json, figures_dir, output_dir)

        # main.c has: main, init, process
        main_md = open(os.path.join(output_dir, "main.md"), "r", encoding="utf-8").read()
        assert "## main" in main_md
        assert "## init" in main_md
        assert "## process" in main_md

    def test_group_by_file_via_generate_function_md(self, sample_functions, sample_types_json, tmp_path):
        output_dir = str(tmp_path / "md_group_file")
        figures_dir = str(tmp_path / "figures_group")
        os.makedirs(figures_dir)
        for func in sample_functions:
            with open(os.path.join(figures_dir, f"{func['name']}.png"), "w") as f:
                f.write("dummy")

        generate_function_md(
            function_list=sample_functions,
            types_json=sample_types_json,
            figures_dir=figures_dir,
            output_dir=output_dir,
            group_by="file",
        )

        assert os.path.exists(os.path.join(output_dir, "main.md"))

    def test_default_group_by_is_function(self, sample_functions, sample_types_json, tmp_path):
        output_dir = str(tmp_path / "md_default")
        figures_dir = str(tmp_path / "figures_default")
        os.makedirs(figures_dir)
        for func in sample_functions:
            with open(os.path.join(figures_dir, f"{func['name']}.png"), "w") as f:
                f.write("dummy")

        generate_function_md(
            function_list=sample_functions,
            types_json=sample_types_json,
            figures_dir=figures_dir,
            output_dir=output_dir,
        )

        assert os.path.exists(os.path.join(output_dir, "main.md"))
        assert os.path.exists(os.path.join(output_dir, "init.md"))
        assert os.path.exists(os.path.join(output_dir, "process.md"))


class TestGenerateAppendixMd:
    def test_generates_appendix(self, sample_types_json, tmp_path):
        output_path = str(tmp_path / "appendix.md")
        generate_appendix_md(sample_types_json, output_path)
        assert os.path.exists(output_path)
        content = open(output_path, "r", encoding="utf-8").read()
        assert "Appendix Global Data Structures" in content
        assert "Point" in content
        assert "Direction" in content
        assert "BYTE" in content

    def test_uses_a_reference_labels(self, sample_types_json, tmp_path):
        output_path = str(tmp_path / "appendix2.md")
        generate_appendix_md(sample_types_json, output_path)
        content = open(output_path, "r", encoding="utf-8").read()
        assert "A_1" in content
        assert "A_2" in content
        assert "A_3" in content

    def test_missing_types_file(self, tmp_path):
        output_path = str(tmp_path / "appendix_missing.md")
        generate_appendix_md("/nonexistent/path.json", output_path)
        # Should not crash, just log warning

    def test_type_description(self, sample_types_json, tmp_path):
        output_path = str(tmp_path / "appendix_desc.md")
        generate_appendix_md(sample_types_json, output_path)
        content = open(output_path, "r", encoding="utf-8").read()
        assert "2D coordinate point" in content
