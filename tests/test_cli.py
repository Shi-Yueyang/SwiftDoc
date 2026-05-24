import argparse
import logging
import os
import sys
import tempfile
import pytest

from cli import (
    configure_logging,
    validate_paths,
    build_parser,
    main,
)


class TestConfigureLogging:
    def test_default_log_level_is_info(self):
        configure_logging(verbose=False)
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_verbose_sets_debug_level(self):
        configure_logging(verbose=True)
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_verbose_includes_module_name_in_format(self):
        configure_logging(verbose=True)
        root = logging.getLogger()
        handler = root.handlers[0] if root.handlers else None
        if handler:
            fmt = handler.formatter._fmt
            assert "name" in fmt

    def test_third_party_loggers_are_suppressed(self):
        configure_logging(verbose=True)
        assert logging.getLogger("matplotlib").level == logging.INFO
        assert logging.getLogger("PIL").level == logging.INFO
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING


class TestValidatePaths:
    def test_analyse_dir_inside_root_dir_passes(self, tmp_dir):
        sub = os.path.join(tmp_dir, "sub")
        os.makedirs(sub)
        validate_paths(tmp_dir, [sub])

    def test_multiple_analyse_dirs_pass(self, tmp_dir):
        sub1 = os.path.join(tmp_dir, "sub1")
        sub2 = os.path.join(tmp_dir, "sub2")
        os.makedirs(sub1)
        os.makedirs(sub2)
        validate_paths(tmp_dir, [sub1, sub2])

    def test_analyse_dir_same_as_root_dir_passes(self, tmp_dir):
        validate_paths(tmp_dir, [tmp_dir])

    def test_analyse_dir_outside_root_dir_raises(self, tmp_dir):
        outside = os.path.join(os.path.dirname(tmp_dir), "other")
        os.makedirs(outside, exist_ok=True)
        with pytest.raises(ValueError, match="inside root_dir"):
            validate_paths(tmp_dir, [outside])

    def test_one_bad_dir_in_list_raises(self, tmp_dir):
        sub = os.path.join(tmp_dir, "sub")
        os.makedirs(sub)
        outside = os.path.join(os.path.dirname(tmp_dir), "other")
        os.makedirs(outside, exist_ok=True)
        with pytest.raises(ValueError, match="inside root_dir"):
            validate_paths(tmp_dir, [sub, outside])

    def test_analyse_dir_on_different_drive_raises(self, tmp_dir):
        with pytest.raises(ValueError):
            validate_paths(tmp_dir, ["Z:\\nonexistent"])


class TestBuildParser:
    def test_parser_has_generate_subcommand(self):
        p = build_parser("/tmp/cache")
        p.print_help()
        # generate should be a valid subcommand
        ns = p.parse_args(["generate", "c", "/some/project"])
        assert ns.command == "generate"
        assert ns.root_dir == "/some/project"

    def test_parser_has_config_subcommand(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["config"])
        assert ns.command == "config"
        assert ns.key is None
        assert ns.value is None

    def test_config_subcommand_with_key_value(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["config", "temperature", "0.7"])
        assert ns.key == "temperature"
        assert ns.value == "0.7"

    def test_generate_defaults(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["generate", "c", "/proj"])
        assert ns.ai == "oo"
        assert ns.cache_dir == "/tmp/cache"
        assert ns.output_folder == "out"
        assert ns.analyse_dir is None

    def test_generate_with_ai_on(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["generate", "c", "/proj", "--ai", "on"])
        assert ns.ai == "on"

    def test_generate_with_multiple_analyse_dirs(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["generate", "c", "/proj", "--analyse_dir", "/proj/a", "--analyse_dir", "/proj/b"])
        assert ns.analyse_dir == ["/proj/a", "/proj/b"]

    def test_verbose_flag(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["--verbose", "generate", "c", "/proj"])
        assert ns.verbose is True


class TestMain:
    def test_config_set_key_value(self, tmp_path, monkeypatch, capsys):
        config_path = tmp_path / "aoto-md" / "config.json"
        monkeypatch.setattr("cli.set_config_value", lambda k, v, **kw: str(config_path))
        monkeypatch.setattr("cli.configure_logging", lambda verbose: None)
        monkeypatch.setattr("sys.argv", ["cli.py", "config", "temperature", "0.7"])
        main()
        captured = capsys.readouterr()
        assert "Config updated: temperature = 0.7" in captured.out

    def test_config_set_invalid_key(self, monkeypatch, capsys):
        def raise_val_err(k, v):
            raise ValueError(f"Unknown config key: {k}")
        monkeypatch.setattr("cli.set_config_value", raise_val_err)
        monkeypatch.setattr("cli.configure_logging", lambda verbose: None)
        monkeypatch.setattr("sys.argv", ["cli.py", "config", "bad_key", "val"])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1

    def test_config_interactive(self, monkeypatch):
        called = []
        monkeypatch.setattr("cli.rerun_ai_config_interactive", lambda: called.append(True))
        monkeypatch.setattr("cli.configure_logging", lambda verbose: None)
        monkeypatch.setattr("sys.argv", ["cli.py", "config"])
        main()
        assert len(called) == 1

    def test_generate_validate_paths_fails(self, monkeypatch, tmp_path):
        import cli as cli_module
        monkeypatch.setattr("cli.configure_logging", lambda verbose: None)
        monkeypatch.setattr(
            "sys.argv",
            ["cli.py", "generate", "c", str(tmp_path), "--analyse_dir", "/nonexistent/path"],
        )
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code != 0

