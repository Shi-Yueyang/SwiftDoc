"""Type definitions for the data shapes passed between parser methods."""

from typing import TypedDict


class GlobalVar(TypedDict, total=False):
    name: str
    type: str
    file: str
    kind: str          # "definition" | "extern"
    is_static: bool


class TypeDef(TypedDict, total=False):
    kind: str          # "struct" | "union" | "enum" | "typedef"
    name: str
    members: list[str]
    values: list[str]
    original_type: str
    comment: str | None
    source_file: str
    type_description: str


class TypesData(TypedDict):
    description: str
    type_definitions: dict[str, TypeDef]
    type_references: dict[str, str]


class FuncInput(TypedDict, total=False):
    name: str
    type: str
    kind: str          # "parameter" | "Global variable"
    direction: str     # "in" | "in out"
    type_ref: str
    inputs_description: str
    type_description: str


class FuncReturn(TypedDict, total=False):
    expression: str
    return_description: str


class FuncDef(TypedDict, total=False):
    name: str
    file: str
    start_line: int
    conditional_macros: list[str]
    inputs: list[FuncInput]
    returns: list[FuncReturn]
    body_code: str
    normalized_body: str
    calls: list[str]
    called_by: list[str]
    algorithm_logic: str
