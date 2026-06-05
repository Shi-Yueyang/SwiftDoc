import os
import sys
import platform
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from core.utils import (
    get_default_cache_dir,
    decode_file,
    get_node_text,
    find_identifier,
    iter_progress,
    highlight_message,
    enable_ansi_support,
    filter_source_files_by_analyse_dirs,
)


class TestGetDefaultCacheDir:
    def test_returns_path_object(self):
        path = get_default_cache_dir()
        assert path is not None

    def test_path_contains_swift_doc(self):
        path = get_default_cache_dir()
        assert "swift-doc" in str(path)

    @patch("platform.system", return_value="Windows")
    def test_windows_path(self, mock_system):
        path = get_default_cache_dir()
        assert "Cache" in str(path)

    @patch("platform.system", return_value="Darwin")
    def test_macos_path(self, mock_system):
        path = get_default_cache_dir()
        assert "Caches" in str(path)

    @patch("platform.system", return_value="Linux")
    def test_linux_path(self, mock_system):
        path = get_default_cache_dir()
        assert ".cache" in str(path)


class TestDecodeFile:
    def test_utf8_decoding(self):
        data = "Hello, 世界".encode("utf-8")
        result = decode_file(data)
        assert result == "Hello, 世界"

    def test_gb18030_decoding(self):
        # Chinese GB18030 encoded bytes
        data = "中文测试".encode("gb18030")
        result = decode_file(data)
        assert result == "中文测试"

    def test_fallback_with_replace(self):
        # Invalid bytes that can't decode as UTF-8 or GB18030
        data = b"\xff\xfe\x00\x01"
        result = decode_file(data)
        assert isinstance(result, str)

    def test_plain_ascii(self):
        data = b"hello world"
        result = decode_file(data)
        assert result == "hello world"


class TestGetNodeText:
    def test_returns_decoded_text(self):
        mock = MagicMock()
        mock.text = b"hello"
        assert get_node_text(mock) == "hello"


class TestFindIdentifier:
    def test_finds_identifier_directly(self):
        mock = MagicMock()
        mock.type = "identifier"
        assert find_identifier(mock) is mock

    def test_searches_children(self):
        child = MagicMock()
        child.type = "identifier"
        parent = MagicMock()
        parent.type = "declarator"
        parent.children = [child]
        assert find_identifier(parent) is child

    def test_returns_none_when_not_found(self):
        child = MagicMock()
        child.type = "not_identifier"
        child.children = []
        parent = MagicMock()
        parent.type = "declarator"
        parent.children = [child]
        assert find_identifier(parent) is None


class TestIterProgress:
    def test_yields_correct_items(self):
        items = ["a", "b", "c"]
        results = list(iter_progress(items, "Test"))
        assert len(results) == 3
        assert results[0] == (1, 3, "a")
        assert results[1] == (2, 3, "b")
        assert results[2] == (3, 3, "c")

    def test_empty_list(self):
        results = list(iter_progress([], "Test"))
        assert results == []

    def test_single_item(self):
        results = list(iter_progress(["x"], "Test"))
        assert len(results) == 1
        assert results[0] == (1, 1, "x")


class TestHighlightMessage:
    def test_returns_colored_when_tty(self):
        with patch.object(sys.stderr, "isatty", return_value=True):
            result = highlight_message("hello")
            assert "hello" in result
            assert "\033" in result

    def test_returns_plain_when_not_tty(self):
        with patch.object(sys.stderr, "isatty", return_value=False):
            result = highlight_message("hello")
            assert result == "hello"


class TestEnableAnsiSupport:
    def test_runs_on_windows(self):
        # Should not raise on import
        pass


class TestFilterSourceFilesByAnalyseDirs:
    def test_exact_file_match(self, tmp_dir):
        f1 = os.path.join(tmp_dir, "a.c")
        f2 = os.path.join(tmp_dir, "b.c")
        for f in (f1, f2):
            with open(f, "w") as fh:
                fh.write("// test")
        result = filter_source_files_by_analyse_dirs([f1, f2], [f1])
        assert result == [f1]

    def test_directory_match(self, tmp_dir):
        sub = os.path.join(tmp_dir, "sub")
        os.makedirs(sub)
        f1 = os.path.join(sub, "a.c")
        f2 = os.path.join(tmp_dir, "b.c")
        for f in (f1, f2):
            with open(f, "w") as fh:
                fh.write("// test")
        result = filter_source_files_by_analyse_dirs([f1, f2], [sub])
        assert result == [f1]

    def test_mixed_files_and_dirs(self, tmp_dir):
        sub = os.path.join(tmp_dir, "sub")
        os.makedirs(sub)
        f1 = os.path.join(sub, "a.c")
        f2 = os.path.join(tmp_dir, "b.c")
        f3 = os.path.join(tmp_dir, "c.c")
        for f in (f1, f2, f3):
            with open(f, "w") as fh:
                fh.write("// test")
        result = filter_source_files_by_analyse_dirs([f1, f2, f3], [sub, f2])
        assert set(result) == {f1, f2}

    def test_no_match_returns_empty(self, tmp_dir):
        f1 = os.path.join(tmp_dir, "a.c")
        with open(f1, "w") as fh:
            fh.write("// test")
        result = filter_source_files_by_analyse_dirs([f1], ["/nonexistent/file.c"])
        assert result == []

    def test_empty_analyse_dirs_returns_all(self, tmp_dir):
        f1 = os.path.join(tmp_dir, "a.c")
        with open(f1, "w") as fh:
            fh.write("// test")
        result = filter_source_files_by_analyse_dirs([f1], [])
        assert result == [f1]
