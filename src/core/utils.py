import os
import sys
import platform
from pathlib import Path

import chardet


def enable_ansi_support():
    """Enable ANSI escape sequence support on Windows."""
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # Enable virtual terminal processing
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)


enable_ansi_support()


def get_default_cache_dir():
    """Get the default cache directory path for the current platform."""
    home = Path.home()
    if platform.system() == "Windows":
        return Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")) / "aoto-md" / "Cache"
    elif platform.system() == "Darwin":  # macOS
        return home / "Library" / "Caches" / "aoto-md"
    else:  # Linux and others
        return Path(os.environ.get("XDG_CACHE_HOME", home / ".cache")) / "aoto-md"


ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_DIM = "\033[2m"
ANSI_CYAN = "\033[36m"
ANSI_GREEN = "\033[32m"


def highlight_message(message, color=ANSI_CYAN):
    if not sys.stderr.isatty():
        return message
    return f"{ANSI_BOLD}{color}{message}{ANSI_RESET}"

def decode_file(raw_data):
    """Automatically decode file content: prioritize UTF-8, then GB18030, and finally detect encoding with chardet."""
    try:
        return raw_data.decode('utf-8')
    except UnicodeDecodeError:
        pass
    try:
        return raw_data.decode('gb18030')
    except UnicodeDecodeError:
        detected = chardet.detect(raw_data)
        encoding = detected.get('encoding', 'utf-8')
        if encoding and encoding.lower() in ('gb2312', 'gbk', 'gb18030'):
            encoding = 'gb18030'
        return raw_data.decode(encoding, errors='ignore')
    
def get_node_text(node):
    return node.text.decode('utf-8')

def find_identifier(node):
    if node.type == 'identifier':
        return node
    for child in node.children:
        result = find_identifier(child)
        if result:
            return result
    return None


def iter_progress(items, label, width=24):
    total = len(items)
    show_progress = total > 0 and sys.stderr.isatty()

    for index, item in enumerate(items, start=1):
        if show_progress:
            filled = max(1, int(width * index / total))
            head = ">" if index < total else "="
            bar = "=" * max(0, filled - 1) + head + "." * (width - filled)
            percent = int(index * 100 / total)
            sys.stderr.write(
                "\r"
                f"{ANSI_BOLD}{label:<20}{ANSI_RESET} "
                f"{ANSI_CYAN}[{bar}]{ANSI_RESET} "
                f"{ANSI_GREEN}{percent:>3}%{ANSI_RESET} "
                f"{ANSI_DIM}{index}/{total}{ANSI_RESET}"
            )
            sys.stderr.flush()
        yield index, total, item

    if show_progress:
        sys.stderr.write("\n")
        sys.stderr.flush()


_walk_cache = {}


def collect_source_files(project_dir, extensions):
    """Walk project_dir (or handle a single file) and return files matching any of the given extensions.

    Results are cached per (project_dir, extensions) so multiple calls with the same
    arguments reuse the file list and only log counts once.
    """
    cache_key = (os.path.abspath(project_dir), tuple(extensions))
    if cache_key in _walk_cache:
        return _walk_cache[cache_key]

    files = []
    if os.path.isfile(project_dir):
        if any(project_dir.endswith(ext) for ext in extensions):
            files.append(os.path.abspath(project_dir))
    else:
        for root, _, filenames in os.walk(project_dir):
            for f in filenames:
                if any(f.endswith(ext) for ext in extensions):
                    files.append(os.path.abspath(os.path.join(root, f)))
    files.sort()
    _walk_cache[cache_key] = files

    if files:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("Found %s files (%s)", len(files), ", ".join(extensions))
    return files
