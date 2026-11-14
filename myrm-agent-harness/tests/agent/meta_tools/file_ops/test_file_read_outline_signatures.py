"""The regex outline lists a definition whose name is followed by type parameters or a return type.

A pattern that expects ``name(`` right after the name silently drops every generic definition from the outline: the
model is then told a file has no such symbol and has to find it by reading the whole file.
"""

import time

import pytest

from myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.outline import extract_file_outline


def _entries(source: str, path: str) -> list[str]:
    """The ``kind name`` of every outline entry, in file order."""
    outline = extract_file_outline(source, path)
    return [line.split(": ", 1)[1] for line in outline.splitlines()[1:]]


@pytest.mark.parametrize(
    ("source", "path", "expected"),
    [
        pytest.param("export function deferred<T>() {\n}\n", "a.ts", ["function deferred"], id="ts-generic-function"),
        pytest.param(
            "export async function load<T extends Record<string, Array<number>>>(key: T) {\n}\n",
            "a.ts",
            ["async function load"],
            id="ts-generic-function-with-nested-brackets",
        ),
        pytest.param(
            "export type Listener<K extends Key = Key> = (key: K) => void;\n",
            "a.ts",
            ["type Listener"],
            id="ts-generic-type-alias",
        ),
        pytest.param(
            "export const toCamel = <T,>(value: unknown): T => value as T;\n",
            "a.tsx",
            ["const toCamel"],
            id="ts-generic-arrow",
        ),
        pytest.param(
            "export const request = async <T = unknown>(url: string): Promise<T> => fetch(url);\n",
            "a.ts",
            ["const request"],
            id="ts-generic-async-arrow",
        ),
        pytest.param("func Map[T, U any](items []T) []U {\n}\n", "a.go", ["func Map"], id="go-generic-function"),
        pytest.param(
            "func Keys[M ~map[K]V, K comparable, V any](m M) []K {\n}\n",
            "a.go",
            ["func Keys"],
            id="go-generic-constraint-with-brackets",
        ),
        pytest.param("type Stack[T any] struct {\n}\n", "a.go", ["type Stack"], id="go-generic-struct"),
        pytest.param("func (s *Stack[T]) Push(item T) {\n}\n", "a.go", ["func Push"], id="go-generic-receiver"),
        pytest.param(
            # The unclosed call makes the source unparsable, so the regex fallback lists it.
            "def first[T](items: list[T]) -> T:\n    return items[0]\n\nclass Broken(\n",
            "a.py",
            ["def first", "class Broken"],
            id="python-fallback-generic-function",
        ),
    ],
)
def test_generic_definitions_are_listed(source: str, path: str, expected: list[str]) -> None:
    assert _entries(source, path) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("export const resplit = (): void => {\n};\n", ["const resplit"], id="return-type"),
        pytest.param("const run = async (id: string): Promise<void> => {\n};\n", ["const run"], id="async-return-type"),
        pytest.param(
            "export const Panel: FC<Props> = ({ title }) => {\n  return null;\n};\n",
            ["const Panel"],
            id="annotated-variable",
        ),
        pytest.param(
            "const make = (): (() => void) => () => {};\n", ["const make"], id="return-type-that-is-a-function-type"
        ),
        pytest.param("const add = (a: number) => a + 1;\n", ["const add"], id="unchanged-plain-arrow"),
    ],
)
def test_annotated_arrow_functions_are_listed(source: str, expected: list[str]) -> None:
    assert _entries(source, "a.ts") == expected


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("const total = (a + b) * c;\n", id="parenthesised-expression"),
        pytest.param("const label: string = (flag ? 'a' : 'b');\n", id="annotated-parenthesised-expression"),
        pytest.param("const items = useMemo<Item[]>(() => build(), []);\n", id="generic-call"),
        pytest.param("const ok = a < b && c > (d);\n", id="comparison"),
        pytest.param("type = 5;\n", id="identifier-named-type"),
    ],
)
def test_expressions_are_not_listed_as_definitions(source: str) -> None:
    assert _entries(source, "a.ts") == []


def test_a_hostile_one_line_file_is_scanned_in_linear_time() -> None:
    """Unbounded type-parameter matching retries every `>(` against the rest of the line: 180 KB took seconds."""
    hostile = "const a = " + "<>(" * 60_000
    started = time.perf_counter()
    assert extract_file_outline(hostile, "a.ts") == ""
    assert time.perf_counter() - started < 1.0
