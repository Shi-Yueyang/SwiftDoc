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

    def test_third_party_loggers_are_suppressed(self):
        configure_logging(verbose=True)
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
    def test_parser_has_moduledesign_subcommand(self):
        p = build_parser("/tmp/cache")
        p.print_help()
        ns = p.parse_args(["moduledesign", "/some/project"])
        assert ns.command == "moduledesign"
        assert ns.root_dir == "/some/project"
        # argparse.SUPPRESS — attributes only exist when explicitly passed
        assert not hasattr(ns, "lang")

    def test_parser_has_config_subcommand(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["config-ai"])
        assert ns.command == "config-ai"
        assert ns.key is None
        assert ns.value is None

    def test_config_subcommand_with_key_value(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["config-ai", "temperature", "0.7"])
        assert ns.key == "temperature"
        assert ns.value == "0.7"

    def test_moduledesign_defaults(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["moduledesign", "/proj"])
        # argparse.SUPPRESS — unset attributes are absent
        assert not hasattr(ns, "lang")
        assert not hasattr(ns, "ai")
        assert not hasattr(ns, "cache_dir")
        assert not hasattr(ns, "output_folder")
        assert not hasattr(ns, "analyse_dir")

    def test_moduledesign_with_ai_on(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["moduledesign", "/proj", "--ai", "on"])
        assert ns.ai == "on"

    def test_moduledesign_with_ada_lang(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["moduledesign", "/proj", "--lang", "ada"])
        assert ns.lang == "ada"

    def test_moduledesign_with_multiple_analyse_dirs(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["moduledesign", "/proj", "--analyse_dir", "/proj/a", "--analyse_dir", "/proj/b"])
        assert ns.analyse_dir == ["/proj/a", "/proj/b"]

    def test_verbose_flag(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["--verbose", "moduledesign", "/proj"])
        assert ns.verbose is True

    def test_ignore_calls_flag(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["moduledesign", "/proj", "--ignore-calls", "free", "--ignore-calls", "malloc"])
        assert ns.ignore_calls == ["free", "malloc"]

    def test_ignore_types_flag(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["moduledesign", "/proj", "--ignore-types", "noisy_t"])
        assert ns.ignore_types == ["noisy_t"]

    def test_skip_sections_flag(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["moduledesign", "/proj", "--skip-sections", "local_data,algorithm"])
        assert ns.skip_sections == "local_data,algorithm"

    def test_embedded_global_reference_flag_yes(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["moduledesign", "/proj", "--embedded-global-reference", "yes"])
        assert ns.embedded_global_reference == "yes"

    def test_embedded_global_reference_flag_no(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["moduledesign", "/proj", "--embedded-global-reference", "no"])
        assert ns.embedded_global_reference == "no"

    def test_embedded_global_reference_not_present_by_default(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["moduledesign", "/proj"])
        assert not hasattr(ns, "embedded_global_reference")

    def test_embedded_global_reference_rejects_invalid_value(self):
        p = build_parser("/tmp/cache")
        with pytest.raises(SystemExit):
            p.parse_args(["moduledesign", "/proj", "--embedded-global-reference", "maybe"])

    def test_out_param_location_defaults(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["moduledesign", "/proj"])
        assert not hasattr(ns, "out_param_location")

    def test_out_param_location_inputs(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["moduledesign", "/proj", "--out-param-location", "inputs"])
        assert ns.out_param_location == "inputs"

    def test_out_param_location_outputs(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["moduledesign", "/proj", "--out-param-location", "outputs"])
        assert ns.out_param_location == "outputs"

    def test_out_param_location_rejects_invalid_value(self):
        p = build_parser("/tmp/cache")
        with pytest.raises(SystemExit):
            p.parse_args(["moduledesign", "/proj", "--out-param-location", "both"])

    def test_parser_has_createconfig_subcommand(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["md-toml"])
        assert ns.command == "md-toml"
        assert ns.output == "swift-doc.toml"

    def test_createconfig_custom_output(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["md-toml", "-o", "mycfg.toml"])
        assert ns.output == "mycfg.toml"

    def test_createconfig_long_output_flag(self):
        p = build_parser("/tmp/cache")
        ns = p.parse_args(["md-toml", "--output", "/abs/path/cfg.toml"])
        assert ns.output == "/abs/path/cfg.toml"


class TestMain:
    def test_config_set_key_value(self, tmp_path, monkeypatch, capsys):
        config_path = tmp_path / "swift-doc" / "config.json"
        monkeypatch.setattr("cli.set_config_value", lambda k, v, **kw: str(config_path))
        monkeypatch.setattr("cli.configure_logging", lambda verbose: None)
        monkeypatch.setattr("sys.argv", ["cli.py", "config-ai", "temperature", "0.7"])
        main()
        captured = capsys.readouterr()
        assert "Config updated: temperature = 0.7" in captured.out

    def test_config_set_invalid_key(self, monkeypatch, capsys):
        def raise_val_err(k, v):
            raise ValueError(f"Unknown config key: {k}")
        monkeypatch.setattr("cli.set_config_value", raise_val_err)
        monkeypatch.setattr("cli.configure_logging", lambda verbose: None)
        monkeypatch.setattr("sys.argv", ["cli.py", "config-ai", "bad_key", "val"])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1

    def test_config_interactive(self, monkeypatch):
        called = []
        monkeypatch.setattr("cli.rerun_ai_config_interactive", lambda: called.append(True))
        monkeypatch.setattr("cli.configure_logging", lambda verbose: None)
        monkeypatch.setattr("sys.argv", ["cli.py", "config-ai"])
        main()
        assert len(called) == 1

    def test_moduledesign_validate_paths_fails(self, monkeypatch, tmp_path):
        import cli as cli_module
        monkeypatch.setattr("cli.configure_logging", lambda verbose: None)
        monkeypatch.setattr(
            "sys.argv",
            ["cli.py", "moduledesign", "c", str(tmp_path), "--analyse_dir", "/nonexistent/path"],
        )
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code != 0

    def test_createconfig_creates_file(self, tmp_path, monkeypatch, capsys):
        output = tmp_path / "swift-doc.toml"
        monkeypatch.setattr("cli.configure_logging", lambda verbose: None)
        monkeypatch.setattr("sys.argv", ["cli.py", "md-toml", "-o", str(output)])
        main()
        captured = capsys.readouterr()
        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert content.startswith("# swift-doc.toml")
        assert "root_dir" in content
        assert "[ignore]" in content
        assert "[define]" in content
        assert "[sections]" in content
        assert "Created config file:" in captured.out
        assert str(output) in captured.out

    def test_createconfig_fails_if_output_exists(self, tmp_path, monkeypatch, capsys):
        output = tmp_path / "existing.toml"
        output.write_text("# already here\n", encoding="utf-8")
        monkeypatch.setattr("cli.configure_logging", lambda verbose: None)
        monkeypatch.setattr("sys.argv", ["cli.py", "md-toml", "-o", str(output)])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "already exists" in captured.err
        assert output.read_text(encoding="utf-8") == "# already here\n"

    def test_createconfig_default_output_path(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr("cli.configure_logging", lambda verbose: None)
        monkeypatch.setattr("sys.argv", ["cli.py", "md-toml"])
        monkeypatch.chdir(tmp_path)
        main()
        captured = capsys.readouterr()
        expected = os.path.join(str(tmp_path), "swift-doc.toml")
        assert os.path.isfile(expected)
        assert "Created config file:" in captured.out
        assert expected in captured.out


class TestDirectoryShortcut:
    """Tests for the swift-doc <folder> directory shortcut."""

    def test_folder_with_toml_auto_fills_root_dir(self, tmp_path, monkeypatch):
        d = tmp_path / "myproject"
        d.mkdir()
        (d / "swift-doc.toml").write_text("# minimal config\n", encoding="utf-8")

        captured_override = {}

        def fake_run(cli_args, toml_config_override=None):
            captured_override["override"] = toml_config_override

        monkeypatch.setattr("cli.configure_logging", lambda verbose: None)
        monkeypatch.setattr("cli._run_moduledesign", fake_run)
        monkeypatch.setattr("sys.argv", ["swift-doc", str(d)])

        main()

        override = captured_override["override"]
        assert override is not None
        assert override["root_dir"] == os.path.abspath(str(d))

    def test_folder_with_toml_auto_fills_output_folder(self, tmp_path, monkeypatch):
        d = tmp_path / "myproject"
        d.mkdir()
        (d / "swift-doc.toml").write_text("# minimal\n", encoding="utf-8")

        captured_override = {}

        def fake_run(cli_args, toml_config_override=None):
            captured_override["override"] = toml_config_override

        monkeypatch.setattr("cli.configure_logging", lambda verbose: None)
        monkeypatch.setattr("cli._run_moduledesign", fake_run)
        monkeypatch.setattr("sys.argv", ["swift-doc", str(d)])

        main()

        override = captured_override["override"]
        assert override is not None
        output = override["output_folder"]
        prefix = os.path.abspath(str(d)) + os.sep + "moduledesign_"
        assert output.startswith(prefix)
        # timestamp part: YYYY-MM-DD_HHMMSS (17 chars)
        ts_part = output[len(prefix):]
        import re
        assert re.match(r"^\d{4}-\d{2}-\d{2}_\d{6}$", ts_part)

    def test_folder_with_toml_preserves_existing_root_dir(self, tmp_path, monkeypatch):
        d = tmp_path / "myproject"
        d.mkdir()
        (d / "swift-doc.toml").write_text('root_dir = "src"\n', encoding="utf-8")

        captured_override = {}

        def fake_run(cli_args, toml_config_override=None):
            captured_override["override"] = toml_config_override

        monkeypatch.setattr("cli.configure_logging", lambda verbose: None)
        monkeypatch.setattr("cli._run_moduledesign", fake_run)
        monkeypatch.setattr("sys.argv", ["swift-doc", str(d)])

        main()

        override = captured_override["override"]
        expected = os.path.normpath(os.path.join(str(d), "src"))
        assert override["root_dir"] == expected

    def test_folder_with_toml_preserves_existing_output_folder(self, tmp_path, monkeypatch):
        d = tmp_path / "myproject"
        d.mkdir()
        (d / "swift-doc.toml").write_text('output_folder = "my_docs"\n', encoding="utf-8")

        captured_override = {}

        def fake_run(cli_args, toml_config_override=None):
            captured_override["override"] = toml_config_override

        monkeypatch.setattr("cli.configure_logging", lambda verbose: None)
        monkeypatch.setattr("cli._run_moduledesign", fake_run)
        monkeypatch.setattr("sys.argv", ["swift-doc", str(d)])

        main()

        override = captured_override["override"]
        assert override["output_folder"] == "my_docs"

    def test_folder_without_toml_errors(self, tmp_path, monkeypatch, capsys):
        d = tmp_path / "empty_project"
        d.mkdir()

        monkeypatch.setattr("sys.argv", ["swift-doc", str(d)])

        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "swift-doc.toml" in captured.err

    def test_folder_with_verbose_reorders_argv(self, tmp_path, monkeypatch):
        d = tmp_path / "myproject"
        d.mkdir()
        (d / "swift-doc.toml").write_text("# minimal\n", encoding="utf-8")

        captured_argv = {}

        def fake_run(cli_args, toml_config_override=None):
            captured_argv["argv"] = list(sys.argv)

        monkeypatch.setattr("cli.configure_logging", lambda verbose: None)
        monkeypatch.setattr("cli._run_moduledesign", fake_run)
        monkeypatch.setattr("sys.argv", ["swift-doc", str(d), "--verbose"])

        main()

        argv = captured_argv["argv"]
        verbose_idx = argv.index("--verbose")
        md_idx = argv.index("md")
        assert verbose_idx < md_idx
        assert str(d) in argv

    def test_folder_passes_toml_override(self, tmp_path, monkeypatch):
        d = tmp_path / "myproject"
        d.mkdir()
        (d / "swift-doc.toml").write_text('lang = "c"\n', encoding="utf-8")

        captured = {}

        def fake_run(cli_args, toml_config_override=None):
            captured["override"] = toml_config_override
            captured["called"] = True

        monkeypatch.setattr("cli.configure_logging", lambda verbose: None)
        monkeypatch.setattr("cli._run_moduledesign", fake_run)
        monkeypatch.setattr("sys.argv", ["swift-doc", str(d)])

        main()

        assert captured.get("called")
        override = captured["override"]
        assert override is not None
        assert override["lang"] == "c"
        assert override["root_dir"] == os.path.abspath(str(d))

