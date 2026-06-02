import os
import json
import pytest

from generators.images import (
    estimate_text_units,
    get_box_width,
    get_box_height,
    generate_function_graphs,
)


class TestEstimateTextUnits:
    def test_empty_string(self):
        assert estimate_text_units("") == 0.0

    def test_plain_ascii(self):
        result = estimate_text_units("hello")
        assert result == 5.0

    def test_uppercase_weighted(self):
        result = estimate_text_units("ABC")
        assert result > 3.0  # uppercase chars weigh more

    def test_underscore_weighted(self):
        result = estimate_text_units("_")
        assert result == 1.3

    def test_digits_weighted(self):
        result = estimate_text_units("123")
        assert result > 3.0

    def test_unicode_weighted(self):
        result = estimate_text_units("中文")
        assert result > 2.0

    def test_mixed(self):
        result = estimate_text_units("hello_world")
        assert result > 11.0  # underscore adds extra


class TestGetBoxWidth:
    def test_minimum_width(self):
        width = get_box_width("x")
        assert width >= 2.0

    def test_longer_text_wider(self):
        short = get_box_width("a")
        long = get_box_width("a_very_long_function_name")
        assert long > short

    def test_accepts_custom_char_width(self):
        long_text = "a_very_long_function_name_with_underscores"
        w1 = get_box_width(long_text, char_width=0.05, min_width=1.0)
        w2 = get_box_width(long_text, char_width=0.2, min_width=1.0)
        assert w2 > w1

    def test_larger_fontsize_produces_wider_box(self):
        text = "some_function_name"
        w1 = get_box_width(text, fontsize=11)
        w2 = get_box_width(text, fontsize=16)
        assert w2 > w1

    def test_fontsize_scales_min_width(self):
        w1 = get_box_width("x", fontsize=11, min_width=3.0)
        w2 = get_box_width("x", fontsize=22, min_width=3.0)
        assert w2 > w1


class TestGetBoxHeight:
    def test_returns_positive_value(self):
        h = get_box_height(11)
        assert h > 0

    def test_larger_fontsize_produces_taller_box(self):
        h1 = get_box_height(11)
        h2 = get_box_height(16)
        assert h2 > h1


class TestGenerateFunctionGraphs:
    def test_generates_images(self, sample_functions, tmp_path):
        output_dir = str(tmp_path / "graph_output")
        generate_function_graphs(function_list=sample_functions, output_dir=output_dir)
        assert os.path.isdir(output_dir)
        for func in sample_functions:
            img_path = os.path.join(output_dir, f"{func['name']}.png")
            assert os.path.exists(img_path), f"Missing image for {func['name']}"

    def test_empty_list_does_not_crash(self, tmp_path):
        output_dir = str(tmp_path / "empty_graphs")
        generate_function_graphs(function_list=[], output_dir=output_dir)

    def test_single_function_no_callers_or_callees(self, tmp_path):
        output_dir = str(tmp_path / "solo_graph")
        func = [{
            "name": "solo",
            "calls": [],
            "called_by": [],
        }]
        generate_function_graphs(function_list=func, output_dir=output_dir)
        img_path = os.path.join(output_dir, "solo.png")
        assert os.path.exists(img_path)

    def test_function_with_callers(self, tmp_path):
        output_dir = str(tmp_path / "caller_graph")
        func = [{
            "name": "target",
            "calls": [],
            "called_by": ["caller1", "caller2"],
        }]
        generate_function_graphs(function_list=func, output_dir=output_dir)
        assert os.path.exists(os.path.join(output_dir, "target.png"))

    def test_function_with_callees(self, tmp_path):
        output_dir = str(tmp_path / "callee_graph")
        func = [{
            "name": "caller",
            "calls": ["callee1", "callee2"],
            "called_by": [],
        }]
        generate_function_graphs(function_list=func, output_dir=output_dir)
        assert os.path.exists(os.path.join(output_dir, "caller.png"))

    def test_function_with_special_chars_in_name(self, tmp_path):
        output_dir = str(tmp_path / "special_chars")
        func = [{
            "name": "func:with/special\\chars",
            "calls": [],
            "called_by": [],
        }]
        generate_function_graphs(function_list=func, output_dir=output_dir)
        safe_name = "func_with_special_chars"
        assert os.path.exists(os.path.join(output_dir, f"{safe_name}.png"))

    def test_generated_image_is_non_empty(self, sample_functions, tmp_path):
        output_dir = str(tmp_path / "non_empty_test")
        generate_function_graphs(function_list=sample_functions[:1], output_dir=output_dir)
        img_path = os.path.join(output_dir, f"{sample_functions[0]['name']}.png")
        size = os.path.getsize(img_path)
        assert size > 100  # image should have some content

    def test_plain_style_generates_images(self, sample_functions, tmp_path):
        output_dir = str(tmp_path / "plain_graph_output")
        generate_function_graphs(function_list=sample_functions, output_dir=output_dir, style="plain")
        assert os.path.isdir(output_dir)
        for func in sample_functions:
            img_path = os.path.join(output_dir, f"{func['name']}.png")
            assert os.path.exists(img_path), f"Missing image for {func['name']} with plain style"

    def test_plain_style_image_is_non_empty(self, sample_functions, tmp_path):
        output_dir = str(tmp_path / "plain_non_empty_test")
        generate_function_graphs(function_list=sample_functions[:1], output_dir=output_dir, style="plain")
        img_path = os.path.join(output_dir, f"{sample_functions[0]['name']}.png")
        size = os.path.getsize(img_path)
        assert size > 100
