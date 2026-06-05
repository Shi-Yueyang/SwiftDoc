"""TOML project config loader.

Reads a swift-doc.toml (or any named) config file that can hold all
CLI parameters plus ignore lists for calls and types.
"""

import os
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


# Keys that can appear at the top level of a TOML config.
_TOP_LEVEL_KEYS = {
    "root_dir", "lang", "output_folder", "cache_dir",
    "format", "group_by", "style", "ai", "analyse_dirs",
}

# Keys that appear under [ignore]
_IGNORE_KEYS = {"calls", "types"}

# Default config filename to auto-discover
DEFAULT_CONFIG_NAME = "swift-doc.toml"


def load_toml(path: str) -> dict:
    """Parse a TOML config file and return a flat config dict.

    Returns a dict with string keys.  Keys not present in the file
    are set to None so that the caller can distinguish "not set"
    from "set to an empty value".

    Schema returned::

        {
            "root_dir": str | None,
            "lang": str | None,
            "output_folder": str | None,
            "cache_dir": str | None,
            "format": str | None,
            "group_by": str | None,
            "style": str | None,
            "ai": str | None,
            "analyse_dirs": list[str] | None,
            "ignore_calls": list[str] | None,
            "ignore_types": list[str] | None,
        }
    """
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    config: dict = {}

    # Top-level keys
    for key in _TOP_LEVEL_KEYS:
        val = raw.get(key)
        if val is not None and not isinstance(val, str) and key != "analyse_dirs":
            val = str(val)
        config[key] = val

    # analyse_dirs can be a list of strings
    config["analyse_dirs"] = raw.get("analyse_dirs")

    # [ignore] section
    ignore = raw.get("ignore", {})
    config["ignore_calls"] = ignore.get("calls")
    config["ignore_types"] = ignore.get("types")
    config["ignore_kinds"] = ignore.get("kinds")

    # [define] section
    define = raw.get("define", {})
    config["define_macros"] = define.get("macros")

    return config


def find_config(search_dir: str) -> str | None:
    """Look for swift-doc.toml in *search_dir*.

    Returns the absolute path if found, or None.
    """
    candidate = os.path.join(search_dir, DEFAULT_CONFIG_NAME)
    if os.path.isfile(candidate):
        return os.path.abspath(candidate)
    return None
