import os
import pytest
from parsers import detect_language


class TestDetectLanguage:
    def test_empty_directory_falls_back_to_c(self, tmp_path):
        result = detect_language(str(tmp_path))
        assert result == "c"

    def test_c_files_only(self, tmp_path):
        (tmp_path / "main.c").write_text("int main() {}")
        (tmp_path / "utils.c").write_text("void foo() {}")
        result = detect_language(str(tmp_path))
        assert result == "c"

    def test_adb_files_only(self, tmp_path):
        (tmp_path / "main.adb").write_text("procedure Main is begin null; end Main;")
        (tmp_path / "spi.adb").write_text("procedure Spi_Init is begin null; end Spi_Init;")
        result = detect_language(str(tmp_path))
        assert result == "ada"

    def test_mixed_c_majority(self, tmp_path):
        for name in ("a.c", "b.c", "c.c"):
            (tmp_path / name).write_text("")
        (tmp_path / "d.adb").write_text("")
        result = detect_language(str(tmp_path))
        assert result == "c"

    def test_mixed_ada_majority(self, tmp_path):
        (tmp_path / "a.c").write_text("")
        for name in ("b.adb", "c.adb", "d.adb"):
            (tmp_path / name).write_text("")
        result = detect_language(str(tmp_path))
        assert result == "ada"

    def test_tie_goes_to_ada_alphabetically(self, tmp_path):
        (tmp_path / "a.c").write_text("")
        (tmp_path / "b.c").write_text("")
        (tmp_path / "x.adb").write_text("")
        (tmp_path / "y.adb").write_text("")
        result = detect_language(str(tmp_path))
        assert result == "ada"

    def test_header_only_project(self, tmp_path):
        (tmp_path / "types.h").write_text("typedef int foo;")
        (tmp_path / "config.h").write_text("#define BAR 1")
        result = detect_language(str(tmp_path))
        assert result == "c"

    def test_ads_only_project(self, tmp_path):
        (tmp_path / "types.ads").write_text("package Types is end Types;")
        result = detect_language(str(tmp_path))
        assert result == "ada"

    def test_single_c_file_as_root(self, tmp_path):
        f = tmp_path / "main.c"
        f.write_text("int main() {}")
        result = detect_language(str(f))
        assert result == "c"

    def test_single_adb_file_as_root(self, tmp_path):
        f = tmp_path / "main.adb"
        f.write_text("procedure Main is begin null; end Main;")
        result = detect_language(str(f))
        assert result == "ada"

    def test_no_matching_extensions_falls_back(self, tmp_path):
        (tmp_path / "readme.txt").write_text("hello")
        (tmp_path / "data.csv").write_text("a,b,c")
        result = detect_language(str(tmp_path))
        assert result == "c"

    def test_nested_directories(self, tmp_path):
        sub = tmp_path / "src"
        sub.mkdir()
        (sub / "main.adb").write_text("")
        (sub / "utils.ads").write_text("")
        result = detect_language(str(tmp_path))
        assert result == "ada"

    def test_mixed_headers_and_sources(self, tmp_path):
        (tmp_path / "main.adb").write_text("")
        (tmp_path / "types.ads").write_text("")
        (tmp_path / "legacy.c").write_text("")
        (tmp_path / "legacy.h").write_text("")
        result = detect_language(str(tmp_path))
        assert result == "ada"
