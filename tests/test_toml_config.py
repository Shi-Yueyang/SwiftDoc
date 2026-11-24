import os
from config.toml_config import load_toml, DEFAULT_CONFIG_TEMPLATE


class TestLoadToml:
    def test_top_level_and_section_keys_are_flattened(self, tmp_path):
        cfg = tmp_path / "swift-doc.toml"
        cfg.write_text(
            "\n".join([
                'root_dir = "src"',
                'ai = "off"',
                "ai_workers = 3",
                "verbose = true",
                'analyse_dirs = ["src/a", "src/b.c"]',
                "[ignore]",
                'calls = ["free"]',
                'kinds = ["typedef"]',
                "[define]",
                'macros = ["DEBUG"]',
                "[sections]",
                "algorithm = false",
            ]) + "\n",
            encoding="utf-8",
        )
        config = load_toml(str(cfg))
        assert config["root_dir"] == "src"
        assert config["ai"] == "off"
        assert config["ai_workers"] == "3"  # scalars are stringified
        assert config["verbose"] is True    # bools stay bool
        assert config["analyse_dirs"] == ["src/a", "src/b.c"]
        assert config["ignore_calls"] == ["free"]
        assert config["ignore_kinds"] == ["typedef"]
        assert config["define_macros"] == ["DEBUG"]
        assert config["sections"]["algorithm"] is False
        assert config["sections"]["interface"] is True

    def test_absent_keys_are_none(self, tmp_path):
        cfg = tmp_path / "swift-doc.toml"
        cfg.write_text('root_dir = "."\n', encoding="utf-8")
        config = load_toml(str(cfg))
        assert config["verbose"] is None
        assert config["cache_dir"] is None
        assert config["analyse_dirs"] is None
        # type defaults to the single supported document type
        assert config["type"] == "moduledesign"


class TestDefaultTemplate:
    def test_template_is_loadable_and_has_root_dir(self, tmp_path):
        cfg = tmp_path / "swift-doc.toml"
        cfg.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
        config = load_toml(str(cfg))
        assert config["root_dir"] == "."
        assert config["type"] == "moduledesign"
        assert config["ignore_calls"] == []
        assert config["define_macros"] == []
