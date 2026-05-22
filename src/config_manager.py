import json
import os
import platform
import sys
from getpass import getpass
from pathlib import Path

from openai import OpenAI


CONFIG_LABEL_MAP = {
    "api_key": "AI API key",
    "base_url": "AI base URL",
    "model_name": "AI model name",
}

CONFIG_JSON_MAP = {
    "api_key": "api_key",
    "base_url": "base_url",
    "model_name": "model_name",
}

OPTIONAL_CONFIG_JSON_MAP = {
    "temperature": "temperature",
    "max_tokens": "max_tokens",
    "retry_count": "retry_count",
}

OPTIONAL_CONFIG_DEFAULTS = {
    "temperature": 1.0,
    "max_tokens": 800,
    "retry_count": 1,
}

OPTIONAL_CONFIG_TYPES = {
    "temperature": float,
    "max_tokens": int,
    "retry_count": int,
}

REQUIRED_KEYS = tuple(CONFIG_JSON_MAP.keys())
APP_DIR_NAME = "aoto-md"

ANSI_RESET = "\033[0m"
ANSI_STYLES = {
    "accent": "\033[96m",
    "success": "\033[92m",
    "warning": "\033[93m",
    "error": "\033[91m",
    "muted": "\033[90m",
    "bold": "\033[1m",
}


def _supports_color():
    return sys.stdout.isatty() and os.getenv("NO_COLOR") is None


def _style(text, *style_names):
    if not _supports_color():
        return text
    prefix = "".join(ANSI_STYLES[name] for name in style_names)
    return f"{prefix}{text}{ANSI_RESET}"


def _print_status(label, message, tone="accent"):
    print(f"{_style(label, 'bold', tone)} {message}")


def get_config_path():
    system_name = platform.system()
    home = Path.home()

    if system_name == "Windows":
        base_dir = Path(os.getenv("APPDATA", home / "AppData" / "Roaming"))
    elif system_name == "Darwin":
        base_dir = home / "Library" / "Application Support"
    else:
        base_dir = Path(os.getenv("XDG_CONFIG_HOME", home / ".config"))

    return base_dir / APP_DIR_NAME / "config.json"


def _read_json_file(file_path):
    try:
        with file_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"User config file is not valid JSON: {file_path}") from exc
    except OSError as exc:
        raise RuntimeError(f"Unable to read user config file: {file_path}") from exc


def _normalize_config(raw_config, mapping):
    normalized = {}
    for key, source_key in mapping.items():
        value = raw_config.get(source_key)
        if value is None:
            continue
        value = str(value).strip()
        if value:
            normalized[key] = value
    return normalized


def _normalize_optional_config(raw_config):
    """Load optional config keys (temperature, max_tokens, retry_count) with type conversion and defaults."""
    normalized = {}
    for key, source_key in OPTIONAL_CONFIG_JSON_MAP.items():
        value = raw_config.get(source_key)
        if value is None or (isinstance(value, str) and not value.strip()):
            normalized[key] = OPTIONAL_CONFIG_DEFAULTS[key]
            continue
        try:
            normalized[key] = OPTIONAL_CONFIG_TYPES[key](value)
        except (ValueError, TypeError):
            normalized[key] = OPTIONAL_CONFIG_DEFAULTS[key]
    return normalized


def load_user_config(config_path=None):
    config_path = config_path or get_config_path()
    raw_config = _read_json_file(config_path)
    if not raw_config:
        return {}, config_path
    normalized = _normalize_config(raw_config, CONFIG_JSON_MAP)
    normalized.update(_normalize_optional_config(raw_config))
    return normalized, config_path


def load_ai_call_params(config_path=None):
    """Load temperature, max_tokens, retry_count from user config (with defaults)."""
    config_path = config_path or get_config_path()
    raw_config = _read_json_file(config_path)
    return _normalize_optional_config(raw_config)


def merge_config_sources(*named_sources):
    merged = {}
    origins = {}
    for source_name, values in named_sources:
        for key, value in values.items():
            if value and key not in merged:
                merged[key] = value
                origins[key] = source_name
    return merged, origins


def is_ai_config_complete(config):
    return all(config.get(key) for key in REQUIRED_KEYS)


def get_missing_ai_keys(config):
    return [key for key in REQUIRED_KEYS if not config.get(key)]


def _format_source_summary(origins, config_path=None):
    labels = []
    for key in REQUIRED_KEYS:
        source_name = origins.get(key, "missing")
        if source_name == "user config" and config_path is not None:
            source_name = f"user config ({config_path})"
        labels.append(f"{key}={source_name}")
    return ", ".join(labels)


def resolve_ai_config():
    user_config, config_path = load_user_config()
    merged, origins = merge_config_sources(("user config", user_config))
    details = {
        "origins": origins,
        "config_path": config_path,
        "source_summary": _format_source_summary(origins, config_path),
    }
    return merged, details


def _build_openai_client(config):
    return OpenAI(api_key=config["api_key"], base_url=config["base_url"], timeout=20.0)


def test_ai_connection(config):
    try:
        client = _build_openai_client(config)
        client.chat.completions.create(
            model=config["model_name"],
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
    except Exception as exc:
        raise RuntimeError(f"Connection test failed: {type(exc).__name__}: {exc}") from exc


def save_user_config(config, config_path=None):
    config_path = config_path or get_config_path()
    # Preserve existing optional values from disk so onboarding doesn't strip them
    existing_raw = _read_json_file(config_path)
    payload = {json_key: config[key] for key, json_key in CONFIG_JSON_MAP.items()}
    for key, json_key in OPTIONAL_CONFIG_JSON_MAP.items():
        if json_key in existing_raw:
            payload[json_key] = existing_raw[json_key]

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(config_path.parent, 0o700)
        with config_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        if os.name != "nt":
            os.chmod(config_path, 0o600)
    except OSError as exc:
        raise RuntimeError(f"Unable to write user config file: {config_path}") from exc

    return config_path


def _prompt_value(label, current_value=None, secret=False):
    prompt = f"{label}"
    if current_value:
        prompt += " [press Enter to keep current value]"
    prompt += ": "
    entered = getpass(prompt) if secret else input(prompt)
    entered = entered.strip()
    if entered:
        return entered
    return current_value or ""


def _prompt_yes_no(label, default=False):
    suffix = " [y/N]: " if not default else " [Y/n]: "
    while True:
        answer = input(f"{label}{suffix}").strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        _print_status("Hint", "Enter y or n.", "muted")


def run_ai_onboarding(existing_config=None):
    existing_config = existing_config or {}

    while True:
        try:
            candidate = {
                "api_key": _prompt_value("AI API key", existing_config.get("api_key"), secret=True),
                "base_url": _prompt_value("AI base URL", existing_config.get("base_url")),
                "model_name": _prompt_value("AI model name", existing_config.get("model_name")),
            }
        except KeyboardInterrupt as exc:
            raise SystemExit("AI onboarding interrupted.") from exc

        missing_keys = get_missing_ai_keys(candidate)
        if missing_keys:
            _print_status(
                "Missing",
                ", ".join(CONFIG_LABEL_MAP[key] for key in missing_keys),
                "warning",
            )
            existing_config.update(candidate)
            continue

        _print_status("Check", "Testing AI connection...", "accent")
        try:
            test_ai_connection(candidate)
        except RuntimeError as exc:
            _print_status("Failed", str(exc), "error")
            try:
                should_save = _prompt_yes_no("Save these settings anyway?", default=False)
            except KeyboardInterrupt as interrupt:
                raise SystemExit("AI onboarding interrupted.") from interrupt
            if should_save:
                config_path = save_user_config(candidate)
                _print_status("Saved", f"AI config -> {config_path}", "success")
                return candidate, config_path
            _print_status("Retry", "Re-enter your settings.", "warning")
            existing_config.update(candidate)
            continue

        config_path = save_user_config(candidate)
        _print_status("Saved", f"AI config -> {config_path}", "success")
        return candidate, config_path


def ensure_ai_config_interactive():
    merged_config, details = resolve_ai_config()
    if is_ai_config_complete(merged_config):
        _print_status("Ready", f"Using {details['config_path']}", "success")
        _ensure_optional_config_defaults(details['config_path'])
        return merged_config, details

    if not sys.stdin.isatty():
        missing = ", ".join(CONFIG_LABEL_MAP[key] for key in get_missing_ai_keys(merged_config))
        raise RuntimeError(
            "AI is enabled but configuration is incomplete and interactive onboarding is unavailable. "
            f"Missing: {missing}. Checked {details['source_summary']}"
        )

    missing = ", ".join(CONFIG_LABEL_MAP[key] for key in get_missing_ai_keys(merged_config))
    print(_style("AI setup", "bold", "accent"))
    print(f"  {_style('Missing:', 'warning')} {missing}")
    print(f"  {_style('Target:', 'muted')} {details['config_path']}")
    run_ai_onboarding(merged_config)
    merged_config, details = resolve_ai_config()
    _ensure_optional_config_defaults(details['config_path'])
    return merged_config, details


def _ensure_optional_config_defaults(config_path):
    """Ensure optional config keys (temperature, max_tokens, retry_count) exist in config file with defaults."""
    raw_config = _read_json_file(config_path)
    updated = False
    for key, json_key in OPTIONAL_CONFIG_JSON_MAP.items():
        if json_key not in raw_config:
            raw_config[json_key] = OPTIONAL_CONFIG_DEFAULTS[key]
            updated = True

    if updated:
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            if os.name != "nt":
                os.chmod(config_path.parent, 0o700)
            with config_path.open("w", encoding="utf-8") as handle:
                json.dump(raw_config, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            if os.name != "nt":
                os.chmod(config_path, 0o600)
        except OSError as exc:
            raise RuntimeError(f"Unable to write user config file: {config_path}") from exc


def set_config_value(key, value, config_path=None):
    """Set a single config key to a value. Supports both required and optional keys."""
    config_path = config_path or get_config_path()
    raw_config = _read_json_file(config_path)

    # Determine the JSON key name
    json_key = None
    if key in CONFIG_JSON_MAP:
        json_key = CONFIG_JSON_MAP[key]
    elif key in OPTIONAL_CONFIG_JSON_MAP:
        json_key = OPTIONAL_CONFIG_JSON_MAP[key]
    else:
        raise ValueError(f"Unknown config key: {key}. Valid keys: {list(CONFIG_JSON_MAP.keys()) + list(OPTIONAL_CONFIG_JSON_MAP.keys())}")

    # Type conversion for optional keys
    if key in OPTIONAL_CONFIG_TYPES:
        try:
            value = OPTIONAL_CONFIG_TYPES[key](value)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid value for {key}: expected {OPTIONAL_CONFIG_TYPES[key].__name__}, got: {value}") from exc

    raw_config[json_key] = value

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(config_path.parent, 0o700)
        with config_path.open("w", encoding="utf-8") as handle:
            json.dump(raw_config, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        if os.name != "nt":
            os.chmod(config_path, 0o600)
    except OSError as exc:
        raise RuntimeError(f"Unable to write user config file: {config_path}") from exc

    return config_path


def rerun_ai_config_interactive():
    merged_config, details = resolve_ai_config()

    if not sys.stdin.isatty():
        raise RuntimeError(
            "AI configuration requires an interactive terminal. "
            f"Target: {details['config_path']}"
        )

    print(_style("AI setup", "bold", "accent"))
    print(f"  {_style('Target:', 'muted')} {details['config_path']}")
    if is_ai_config_complete(merged_config):
        print(f"  {_style('Current:', 'muted')} existing values loaded for editing")
    else:
        missing = ", ".join(CONFIG_LABEL_MAP[key] for key in get_missing_ai_keys(merged_config))
        print(f"  {_style('Missing:', 'warning')} {missing}")

    run_ai_onboarding(merged_config)
    return resolve_ai_config()
