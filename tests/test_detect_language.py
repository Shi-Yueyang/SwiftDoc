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
        # unknown extensions don't count, still falls back to c
        ([("a.c", ""), ("b.c", ""), ("c.c", ""), ("d.txt", "")], False, "c"),
        ([("readme.md", ""), ("Makefile", "")], False, "c"),
        # nested directories
        ([("src/main.c", ""), ("src/utils.h", "")], False, "c"),
    ])
    def test_detect_language(self, tmp_path, files, use_file_root, expected):
        for path, content in files:
            full = tmp_path / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content)
        root = str(tmp_path / files[0][0]) if use_file_root else str(tmp_path)
        assert detect_language(root) == expected
