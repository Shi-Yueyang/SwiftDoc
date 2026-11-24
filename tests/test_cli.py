import glob
import json
import logging
import os
import sys
import pytest

from cli import (
    configure_logging,
    validate_paths,
    run_from_config,
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


@pytest.fixture
def captured_phases(monkeypatch):
    """Replace the pipeline phases with recorders and return the record dict."""
    import cli
    calls = {}
    monkeypatch.setattr(cli, "run_extract_phase", lambda args: calls.__setitem__("extract", args))
    monkeypatch.setattr(cli, "run_docgen_phase", lambda args: calls.__setitem__("docgen", args))
    monkeypatch.setattr(cli, "configure_logging", lambda verbose=False: calls.__setitem__("verbose", verbose))
    return calls


def _make_project(tmp_path):
    """A tmp_path with a real C project dir and a configs dir beside it."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "main.c").write_text("int a(void) { return 1; }\n", encoding="utf-8")
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    return proj, cfg_dir


def _write_config(cfg_dir, text):
    path = cfg_dir / "swift-doc.toml"
    path.write_text(text, encoding="utf-8")
    return str(path)


class TestUsage:
    """The single supported usage: swift-doc <config.toml>."""

    def test_no_args_prints_usage_and_fails(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["swift-doc"])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
        assert "Usage:\n  swift-doc <config.toml>" in capsys.readouterr().err

    def test_help_prints_usage_and_exits_zero(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["swift-doc", "--help"])
        main()  # no SystemExit
        assert "Usage:\n  swift-doc <config.toml>" in capsys.readouterr().out

    def test_extra_args_rejected(self, tmp_path, monkeypatch, capsys):
        cfg = _write_config(_make_project(tmp_path)[1], 'root_dir = "."\n')
        monkeypatch.setattr("sys.argv", ["swift-doc", cfg, "--ai", "on"])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "unexpected arguments" in captured.err
        assert "TOML config" in captured.err

    def test_non_toml_argument_rejected(self, tmp_path, monkeypatch, capsys):
        proj = _make_project(tmp_path)[0]
        monkeypatch.setattr("sys.argv", ["swift-doc", str(proj)])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
        assert "expected a .toml config file" in capsys.readouterr().err

    def test_missing_config_file_errors(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["swift-doc", str(tmp_path / "nope.toml")])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
        assert "config file not found" in capsys.readouterr().err


class TestRunFromConfig:
    def test_relative_paths_resolve_against_config_dir(self, tmp_path, captured_phases):
        proj, cfg_dir = _make_project(tmp_path)
        cfg = _write_config(
            cfg_dir,
            'root_dir = "../proj"\noutput_folder = "docs"\ncache_dir = "cache"\n',
        )
        run_from_config(cfg)
        expected_root = os.path.normpath(os.path.join(str(cfg_dir), "..", "proj"))
        extract = captured_phases["extract"]
        docgen = captured_phases["docgen"]
        assert extract.root_dir == expected_root
        assert docgen.output_folder == os.path.normpath(os.path.join(str(cfg_dir), "docs"))
        assert docgen.cache_dir == os.path.normpath(os.path.join(str(cfg_dir), "cache"))

    def test_absolute_paths_pass_through(self, tmp_path, captured_phases):
        proj, cfg_dir = _make_project(tmp_path)
        cfg = _write_config(
            cfg_dir,
            f'root_dir = {json.dumps(str(proj))}\noutput_folder = {str(tmp_path / "out")!r}\n',
        )
        run_from_config(cfg)
        assert captured_phases["extract"].root_dir == str(proj)
        assert captured_phases["docgen"].output_folder == str(tmp_path / "out")

    def test_root_dir_required(self, tmp_path, captured_phases, capsys):
        _, cfg_dir = _make_project(tmp_path)
        cfg = _write_config(cfg_dir, 'format = "docx"\n')
        with pytest.raises(SystemExit) as exc:
            run_from_config(cfg)
        assert exc.value.code == 1
        assert "root_dir is required" in capsys.readouterr().err

    def test_unknown_document_type_errors(self, tmp_path, captured_phases, capsys):
        proj, cfg_dir = _make_project(tmp_path)
        cfg = _write_config(cfg_dir, f'type = "apidoc"\nroot_dir = {json.dumps(str(proj))}\n')
        with pytest.raises(SystemExit) as exc:
            run_from_config(cfg)
        assert exc.value.code == 1
        assert "unknown document type 'apidoc'" in capsys.readouterr().err

    def test_builtin_defaults_applied(self, tmp_path, captured_phases):
        proj, cfg_dir = _make_project(tmp_path)
        cfg = _write_config(cfg_dir, f'root_dir = {json.dumps(str(proj))}\n')
        run_from_config(cfg)
        extract = captured_phases["extract"]
        docgen = captured_phases["docgen"]
        assert docgen.format == "docx"
        assert docgen.group_by == "file"
        assert docgen.style == "plain"
        assert extract.ai == "off"
        assert extract.ai_workers == 6
        assert docgen.out_param_location == "inputs"
        assert docgen.embedded_global_reference == "no"
        # output_folder default resolves next to the config file
        assert docgen.output_folder == os.path.normpath(os.path.join(str(cfg_dir), "out"))
        # analyse_dirs falls back to root_dir
        assert docgen.analyse_dirs == [str(proj)]

    def test_toml_options_passed_through(self, tmp_path, captured_phases):
        proj, cfg_dir = _make_project(tmp_path)
        cfg = _write_config(
            cfg_dir,
            "\n".join([
                f'root_dir = {json.dumps(str(proj))}',
                'format = "markdown"',
                'group_by = "function"',
                'style = "table"',
                'ai = "off"',
                "ai_workers = 3",
                'embedded_global_reference = "yes"',
                'out_param_location = "outputs"',
                "[ignore]",
                'calls = ["free", "malloc"]',
                'types = ["WORD"]',
                'kinds = ["typedef"]',
                "[define]",
                'macros = ["DEBUG"]',
                "[sections]",
                "algorithm = false",
            ]) + "\n",
        )
        run_from_config(cfg)
        extract = captured_phases["extract"]
        docgen = captured_phases["docgen"]
        assert extract.ai_workers == 3
        assert extract.defines == {"DEBUG"}
        assert docgen.format == "markdown"
        assert docgen.group_by == "function"
        assert docgen.style == "table"
        assert docgen.ignore_calls == {"free", "malloc"}
        assert docgen.ignore_types == {"WORD"}
        assert docgen.ignore_kinds == ["typedef"]
        assert docgen.embedded_global_reference == "yes"
        assert docgen.out_param_location == "outputs"
        assert docgen.sections["algorithm"] is False
        assert docgen.sections["interface"] is True

    def test_analyse_dirs_resolved_against_root_dir(self, tmp_path, captured_phases):
        proj, cfg_dir = _make_project(tmp_path)
        (proj / "bsw").mkdir()
        cfg = _write_config(
            cfg_dir,
            f'root_dir = {json.dumps(str(proj))}\nanalyse_dirs = ["bsw"]\n',
        )
        run_from_config(cfg)
        assert captured_phases["docgen"].analyse_dirs == [
            os.path.normpath(os.path.join(str(proj), "bsw"))]

    def test_analyse_dir_outside_root_dir_fails(self, tmp_path, captured_phases, capsys):
        proj, cfg_dir = _make_project(tmp_path)
        cfg = _write_config(
            cfg_dir,
            f'root_dir = {json.dumps(str(proj))}\nanalyse_dirs = ["../cfg"]\n',
        )
        with pytest.raises(SystemExit) as exc:
            run_from_config(cfg)
        assert exc.value.code == 1
        assert "must be inside root_dir" in capsys.readouterr().err

    @pytest.mark.parametrize("key,value", [
        ("format", '"pdf"'),
        ("style", '"neon"'),
        ("group_by", '"folder"'),
        ("ai", '"maybe"'),
        ("out_param_location", '"both"'),
        ("embedded_global_reference", '"maybe"'),
    ])
    def test_invalid_choice_errors(self, tmp_path, captured_phases, capsys, key, value):
        proj, cfg_dir = _make_project(tmp_path)
        cfg = _write_config(cfg_dir, f'root_dir = {json.dumps(str(proj))}\n{key} = {value}\n')
        with pytest.raises(SystemExit) as exc:
            run_from_config(cfg)
        assert exc.value.code == 1
        assert f"invalid {key}" in capsys.readouterr().err

    def test_invalid_ai_workers_errors(self, tmp_path, captured_phases, capsys):
        proj, cfg_dir = _make_project(tmp_path)
        cfg = _write_config(cfg_dir, f'root_dir = {json.dumps(str(proj))}\nai_workers = "many"\n')
        with pytest.raises(SystemExit) as exc:
            run_from_config(cfg)
        assert exc.value.code == 1
        assert "ai_workers must be an integer" in capsys.readouterr().err

    def test_verbose_toml_key_drives_logging(self, tmp_path, captured_phases):
        proj, cfg_dir = _make_project(tmp_path)
        cfg = _write_config(cfg_dir, f'root_dir = {json.dumps(str(proj))}\nverbose = true\n')
        run_from_config(cfg)
        assert captured_phases["verbose"] is True

    def test_verbose_defaults_to_false(self, tmp_path, captured_phases):
        proj, cfg_dir = _make_project(tmp_path)
        cfg = _write_config(cfg_dir, f'root_dir = {json.dumps(str(proj))}\n')
        run_from_config(cfg)
        assert captured_phases["verbose"] is False

    def test_ai_on_triggers_onboarding(self, tmp_path, monkeypatch):
        import cli
        proj, cfg_dir = _make_project(tmp_path)
        cfg = _write_config(cfg_dir, f'root_dir = {json.dumps(str(proj))}\nai = "on"\n')
        called = []
        monkeypatch.setattr(cli, "ensure_ai_config_interactive", lambda: called.append(True))
        monkeypatch.setattr(cli, "run_extract_phase", lambda args: None)
        monkeypatch.setattr(cli, "run_docgen_phase", lambda args: None)
        monkeypatch.setattr(cli, "configure_logging", lambda verbose=False: None)
        run_from_config(cfg)
        assert called == [True]


class TestEndToEnd:
    def test_main_on_small_markdown_project(self, tmp_path, monkeypatch):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "types.h").write_text(
            "typedef struct { int x; int y; } Point;\n",
            encoding="utf-8",
        )
        (proj / "main.c").write_text(
            "int helper(void) { return 2; }\n"
            "Point g_origin;\n"
            "Point a(void) { helper(); return g_origin; }\n",
            encoding="utf-8",
        )
        cfg = tmp_path / "swift-doc.toml"
        cfg.write_text(
            "\n".join([
                f'root_dir = "{proj.name}"',
                'format = "markdown"',
                'style = "table"',
                'ai = "off"',
                'output_folder = "docs_out"',
                'cache_dir = "cache_out"',
            ]) + "\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("sys.argv", ["swift-doc", "swift-doc.toml"])
        main()
        docs = tmp_path / "docs_out"
        assert docs.is_dir()
        md_files = glob.glob(str(docs / "*.md"))
        assert md_files, "no markdown docs generated"
        assert any("appendix" in os.path.basename(p) for p in md_files)
