import os
import pytest
from parsers import detect_language


class TestDetectLanguage:
    @pytest.mark.parametrize("files,use_file_root,expected", [
        # empty / fallback
        ([], False, "c"),
        ([("readme.txt", "hello"), ("data.csv", "a,b,c")], False, "c"),
        # pure C
        ([("main.c", "int main() {}"), ("utils.c", "void foo() {}")], False, "c"),
        ([("types.h", "typedef int foo;"), ("config.h", "#define BAR 1")], False, "c"),
        ([("main.c", "int main() {}")], True, "c"),
        # pure Ada
        ([("main.adb", "procedure Main is begin null; end Main;")], False, "ada"),
        ([("types.ads", "package Types is end Types;")], False, "ada"),
        ([("main.adb", "procedure Main is begin null; end Main;")], True, "ada"),
        # majority wins
        ([("a.c", ""), ("b.c", ""), ("c.c", ""), ("d.adb", "")], False, "c"),
        ([("a.c", ""), ("b.adb", ""), ("c.adb", ""), ("d.adb", "")], False, "ada"),
        ([("main.adb", ""), ("types.ads", ""), ("legacy.c", ""), ("legacy.h", "")], False, "ada"),
        # tie goes to ada
        ([("a.c", ""), ("b.c", ""), ("x.adb", ""), ("y.adb", "")], False, "ada"),
        # nested directories
        ([("src/main.adb", ""), ("src/utils.ads", "")], False, "ada"),
    ])
    def test_detect_language(self, tmp_path, files, use_file_root, expected):
        for path, content in files:
            full = tmp_path / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content)
        root = str(tmp_path / files[0][0]) if use_file_root else str(tmp_path)
        assert detect_language(root) == expected
