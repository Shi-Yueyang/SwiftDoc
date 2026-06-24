import os
import sys
import json
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def sample_c_file(tmp_dir):
    """Create a minimal C file for testing parsers."""
    content = """
static int counter = 0;
int global_mode = 1;

int add(int a, int b) {
    counter = counter + a + b;
    return counter;
}

void set_mode(int mode) {
    global_mode = mode;
}

int get_counter(void) {
    return counter;
}
"""
    path = os.path.join(tmp_dir, "sample.c")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


@pytest.fixture
def sample_h_file(tmp_dir):
    """Create a minimal header file for testing parsers."""
    content = """
#ifndef SAMPLE_H
#define SAMPLE_H

extern int global_mode;
extern int debug_flag;

/* A simple struct for testing */
typedef struct {
    int x;
    int y;
} Point;

// An enum for direction
typedef enum {
    DIR_NORTH,
    DIR_SOUTH,
    DIR_EAST,
    DIR_WEST
} Direction;

typedef unsigned char BYTE;
typedef BYTE DEVICE_ID[3];

#endif
"""
    path = os.path.join(tmp_dir, "sample.h")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


@pytest.fixture
def sample_c_project(tmp_dir, sample_c_file, sample_h_file):
    """A temp directory with both .c and .h files."""
    return tmp_dir


@pytest.fixture
def mock_config_json(tmp_path):
    """Create a mock config JSON file."""
    config = {
        "api_key": "sk-test-key",
        "base_url": "https://api.example.com/v1",
        "model_name": "test-model",
        "temperature": 0.7,
        "max_tokens": 1024,
        "retry_count": 2,
    }
    path = tmp_path / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f)
    return str(path)


@pytest.fixture
def empty_config_json(tmp_path):
    """Create an empty config JSON file."""
    path = tmp_path / "empty_config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({}, f)
    return str(path)


@pytest.fixture
def sample_functions():
    """Sample function data for testing md/image generators."""
    return [
        {
            "name": "main",
            "file": "/project/main.c",
            "start_line": 10,
            "conditional_macros": ["FEATURE_X", "USE_LOG"],
            "inputs": [
                {"name": "argc", "kind": "parameter", "direction": "in", "type": "int", "type_ref": ""},
                {"name": "argv", "kind": "parameter", "direction": "in", "type": "char**", "type_ref": ""},
                {"name": "global_mode", "kind": "Global variable", "direction": "in", "type": "int", "type_ref": ""},
            ],
            "returns": [{"expression": "0", "return_description": "Success exit code"}],
            "body_code": "return 0;",
            "normalized_body": "return0;",
            "calls": ["init", "process"],
            "called_by": [],
            "algorithm_logic": "Entry point that initializes and processes.",
            "module_summary": "Program entry point, initializes system and runs main loop.",
        },
        {
            "name": "init",
            "file": "/project/main.c",
            "start_line": 25,
            "conditional_macros": [],
            "inputs": [],
            "returns": [],
            "body_code": "global_mode = 0;",
            "normalized_body": "global_mode=0;",
            "calls": [],
            "called_by": ["main"],
            "algorithm_logic": "Initializes global state.",
            "module_summary": "Initializes global variables and system state.",
        },
        {
            "name": "process",
            "file": "/project/main.c",
            "start_line": 35,
            "conditional_macros": ["DEBUG"],
            "inputs": [
                {"name": "data", "kind": "parameter", "direction": "in", "type": "int", "type_ref": ""},
            ],
            "returns": [{"expression": "data * 2", "return_description": "Doubled input"}],
            "body_code": "return data * 2;",
            "normalized_body": "returndata*2;",
            "calls": [],
            "called_by": ["main"],
            "algorithm_logic": "Processes input data by doubling it.",
            "module_summary": "Processes input data and returns doubled result.",
        },
    ]


@pytest.fixture
def sample_type_definitions():
    """Sample type definitions for testing."""
    return {
        "type_definitions": {
            "Point": {
                "kind": "struct",
                "members": ["int x", "int y"],
                "comment": "A 2D point",
                "type_description": "Represents a 2D coordinate point.",
                "source_file": "/project/types.h",
            },
            "Direction": {
                "kind": "enum",
                "values": ["DIR_NORTH", "DIR_SOUTH", "DIR_EAST", "DIR_WEST"],
                "comment": "Cardinal directions",
                "type_description": "Enum for cardinall directions.",
                "source_file": "/project/types.h",
            },
            "BYTE": {
                "kind": "typedef",
                "original_type": "unsigned char",
                "comment": "Byte type alias",
                "type_description": "Alias for unsigned char.",
                "source_file": "/project/types.h",
            },
        },
        "type_references": {"Point": "A_1", "Direction": "A_2", "BYTE": "A_3"},
    }


@pytest.fixture
def sample_types_json(tmp_path, sample_type_definitions):
    """Write sample type definitions to a temp JSON file."""
    path = tmp_path / "sample_types.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sample_type_definitions, f)
    return str(path)


@pytest.fixture
def sample_globals_json(tmp_path):
    """Write sample global variables to a temp JSON file."""
    data = {
        "globals": [
            {"name": "global_mode", "type": "int", "file": "/project/main.c", "kind": "definition", "is_static": False},
            {"name": "counter", "type": "int", "file": "/project/main.c", "kind": "definition", "is_static": True},
            {"name": "debug_flag", "type": "int", "file": "/project/main.c", "kind": "extern", "is_static": False},
        ]
    }
    path = tmp_path / "sample_globals.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return str(path)
