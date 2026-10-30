"""Unit tests for the TypeScript/JavaScript extractor: symbols, calls, attribution and inheritance."""

from __future__ import annotations

import time

import pytest

from app.services.code_graph.js_ts_extractor import JsTsTreeSitterExtractor
from app.services.code_graph.models import SymbolKind


def _extract(path: str, source: str) -> JsTsTreeSitterExtractor:
    extractor = JsTsTreeSitterExtractor(path, source)
    assert extractor.extract() is True
    return extractor


def _symbols(extractor: JsTsTreeSitterExtractor) -> dict[str, SymbolKind]:
    return {s.qualified_name: s.kind for s in extractor.symbols}


def _calls(extractor: JsTsTreeSitterExtractor) -> list[tuple[str, str]]:
    return [(c.caller, c.callee) for c in extractor.calls]


def test_extracts_classes_functions_inheritance_and_calls() -> None:
    extractor = _extract(
        "auth.ts",
        """
export class AuthService extends BaseAuth {
  async login(token: string) {
    return true;
  }
}

export function validateInput(val: string) {
  if (val.length > 0) {
    checkToken(val);
  }
  return val.length > 0;
}
""",
    )

    assert _symbols(extractor) == {
        "auth": SymbolKind.MODULE,
        "auth.AuthService": SymbolKind.CLASS,
        "auth.AuthService.login": SymbolKind.METHOD,
        "auth.validateInput": SymbolKind.FUNCTION,
    }
    assert [(i.sub_type, i.super_type) for i in extractor.inheritances] == [("auth.AuthService", "BaseAuth")]
    assert _calls(extractor) == [("auth.validateInput", "checkToken")]


@pytest.mark.parametrize(
    ("declaration", "name"),
    [
        ("function plain(a) {", "plain"),
        ("export function exported(a) {", "exported"),
        ("export default function Page(a) {", "Page"),
        ("async function bare(a) {", "bare"),
        ("export async function loader(a) {", "loader"),
        ("function* walk(a) {", "walk"),
        ("export const arrow = (a) => {", "arrow"),
        ("const asyncArrow = async (a) => {", "asyncArrow"),
        ("let expression = function (a) {", "expression"),
        ("var named = function inner(a) {", "named"),
        ("export const typed = async <T,>(a: T): Promise<T> => {", "typed"),
        ("const wrapped = (\n  a: string,\n  b: number,\n): void => {", "wrapped"),
    ],
)
def test_emits_a_function_symbol_for_each_declaration_form(declaration: str, name: str) -> None:
    extractor = _extract("util.tsx", f"// header\n{declaration}\n  return a;\n}}\n")

    symbol = {s.qualified_name: s for s in extractor.symbols}[f"util.{name}"]
    assert (symbol.name, symbol.kind, symbol.file_path, symbol.line_start) == (name, SymbolKind.FUNCTION, "util.tsx", 2)


def test_a_symbol_spans_from_its_name_to_the_end_of_its_body() -> None:
    extractor = _extract("a.ts", "// c\nexport const run = (x) => {\n  go(x);\n  return x;\n};\n")

    symbol = {s.qualified_name: s for s in extractor.symbols}["a.run"]
    assert (symbol.line_start, symbol.line_end) == (2, 5)


def test_members_of_a_class_are_methods_named_under_the_class() -> None:
    extractor = _extract(
        "box.ts",
        """
class Box<T> {
  #secret = 1;
  handle = () => { this.save(); };
  fixed = 3;
  constructor(private value: T) { super(); }
  get size() { return count(); }
  static create() { return new Box(1); }
  area(): number;
  area(scale?: number) { return scale; }
}
""",
    )

    assert _symbols(extractor) == {
        "box": SymbolKind.MODULE,
        "box.Box": SymbolKind.CLASS,
        "box.Box.handle": SymbolKind.METHOD,
        "box.Box.constructor": SymbolKind.METHOD,
        "box.Box.size": SymbolKind.METHOD,
        "box.Box.create": SymbolKind.METHOD,
        "box.Box.area": SymbolKind.METHOD,
    }
    assert _calls(extractor) == [
        ("box.Box.handle", "this.save"),
        ("box.Box.size", "count"),
        ("box.Box.create", "Box"),
    ]


def test_object_literal_members_and_anonymous_functions_are_not_symbols() -> None:
    extractor = _extract(
        "view.ts",
        """
export function setup() {
  const handlers = { onOpen() { open(); }, onClose: () => close() };
  items.forEach((item) => visit(item));
  return handlers;
}
""",
    )

    assert set(_symbols(extractor)) == {"view", "view.setup"}
    assert _calls(extractor) == [
        ("view.setup", "open"),
        ("view.setup", "close"),
        ("view.setup", "items.forEach"),
        ("view.setup", "visit"),
    ]


def test_a_call_belongs_to_the_innermost_named_function() -> None:
    extractor = _extract(
        "flow.ts",
        """
boot();

export function outer() {
  before();
  function inner() {
    deep();
  }
  const render = () => paint();
  inner();
}
""",
    )

    assert _symbols(extractor)["flow.outer.inner"] is SymbolKind.FUNCTION
    assert _symbols(extractor)["flow.outer.render"] is SymbolKind.FUNCTION
    assert _calls(extractor) == [
        ("flow", "boot"),
        ("flow.outer", "before"),
        ("flow.outer.inner", "deep"),
        ("flow.outer.render", "paint"),
        ("flow.outer", "inner"),
    ]


def test_class_body_and_decorator_calls_belong_to_the_enclosing_scope() -> None:
    extractor = _extract(
        "svc.ts",
        """
@Injectable(config())
export class Service {
  @Input(flag()) field = make();
  @Get('x') run() { work(); }
}
""",
    )

    assert _calls(extractor) == [
        ("svc", "Injectable"),
        ("svc", "config"),
        ("svc", "Input"),
        ("svc", "flag"),
        ("svc", "make"),
        ("svc", "Get"),
        ("svc.Service.run", "work"),
    ]


def test_calls_in_default_parameters_belong_to_the_function() -> None:
    extractor = _extract("p.ts", "function load(a = fallback()) { return a; }\n")

    assert _calls(extractor) == [("p.load", "fallback")]


@pytest.mark.parametrize(
    ("call", "callee"),
    [
        ("save(x);", "save"),
        ("this.store.save(x);", "this.store.save"),
        ("api.client.get(x);", "api.client.get"),
        ("load().items.save(x);", "items.save"),
        ("load().save(x);", "save"),
        ("view?.save(x);", "view.save"),
        ("view!.save(x);", "view.save"),
        ("super.save(x);", "save"),
        ("new Thing(x);", "Thing"),
        ("new ns.Thing(x);", "ns.Thing"),
        ("await api.get<string>(x);", "api.get"),
        ("await fetchJson<Result>(x);", "fetchJson"),
    ],
)
def test_the_callee_is_the_dotted_chain_as_written(call: str, callee: str) -> None:
    extractor = _extract("c.ts", f"async function run(x) {{\n  {call}\n}}\n")

    assert callee in {c.callee for c in extractor.calls}


@pytest.mark.parametrize(
    "call",
    ["table[key](x);", "(function () {})();", "import('./lazy');", "super(x);", "styled.div`color: red;`;"],
)
def test_calls_whose_callee_is_not_a_name_are_not_recorded(call: str) -> None:
    extractor = _extract("c.ts", f"function run(x) {{\n  {call}\n}}\n")

    assert extractor.calls == []


def test_only_the_name_part_of_a_call_result_that_is_called_again_is_recorded() -> None:
    extractor = _extract("c.ts", "function run(x) {\n  factory()(x);\n}\n")

    assert _calls(extractor) == [("c.run", "factory")]


def test_a_call_is_located_at_its_method_name_with_its_argument_count() -> None:
    extractor = _extract(
        "site.ts",
        "run(a, ...rest, /* note */ b);\nclient\n  .get(url)\n  .then((r) => r);\nnew Thing;\n",
    )

    sites = {c.callee: c.call_site for c in extractor.calls}
    assert (sites["run"].line, sites["run"].col, sites["run"].arg_count) == (1, 0, 3)
    assert (sites["client.get"].line, sites["client.get"].col, sites["client.get"].arg_count) == (3, 3, 1)
    assert (sites["then"].line, sites["then"].arg_count) == (4, 1)
    assert (sites["Thing"].line, sites["Thing"].arg_count) == (5, 0)


def test_extends_records_the_base_as_written_and_ignores_implements() -> None:
    extractor = _extract(
        "views.tsx",
        """
export class Panel extends React.Component<Props> implements Closable {}
export class Item extends Base {}
const Dynamic = class extends Mixin(Base) {};
const Plain = class extends Base {};
export default class extends Root {}
""",
    )

    assert [(i.sub_type, i.super_type, i.line) for i in extractor.inheritances] == [
        ("views.Panel", "React.Component", 2),
        ("views.Item", "Base", 3),
        ("views.Plain", "Base", 5),
    ]
    assert _symbols(extractor)["views.Plain"] is SymbolKind.CLASS


def test_typescript_and_tsx_dialects_follow_the_file_extension() -> None:
    assert _symbols(_extract("a.ts", "const f = <T>(x: T) => cast<string>(<any>x);\n"))["a.f"] is SymbolKind.FUNCTION
    jsx = "export const View = () => <button onClick={() => go()}>{label()}</button>;\n"
    for path in ("v.tsx", "v.jsx", "v.js"):
        extractor = _extract(path, jsx)
        assert _symbols(extractor)["v.View"] is SymbolKind.FUNCTION
        assert _calls(extractor) == [("v.View", "go"), ("v.View", "label")]


@pytest.mark.parametrize("broken_line", ["const x = ;", "const y = foo(;", "if (a {", "const z = {a: 1,, b};", "x = 1 +;"])
def test_a_file_with_a_syntax_error_keeps_what_parses(broken_line: str) -> None:
    extractor = _extract(
        "broken.ts",
        f"export function fine() {{ ok(); }}\n{broken_line}\nexport function later() {{ done(); }}\n",
    )

    assert {"broken.fine", "broken.later"} <= set(_symbols(extractor))
    assert ("broken.fine", "ok") in _calls(extractor)
    assert ("broken.later", "done") in _calls(extractor)


def test_a_file_that_cannot_be_recovered_still_keeps_what_came_before() -> None:
    extractor = _extract("broken.ts", "export function fine() { ok(); }\nfunction (\nexport function later() { done(); }\n")

    assert "broken.fine" in _symbols(extractor)


@pytest.mark.parametrize("source", ["", "// only a comment\n", "\ufeff", "\x00\x01\x02", "}}}}{{{{", "`${"])
def test_degenerate_sources_yield_only_the_module_symbol(source: str) -> None:
    extractor = _extract("d.ts", source)

    assert _symbols(extractor) == {"d": SymbolKind.MODULE}
    assert extractor.calls == []


def test_long_call_chains_and_deep_nesting_are_extracted_in_linear_time() -> None:
    chain = "a" + "().b" * 20000 + "();"
    nested = "".join(f"function f{i}() {{ " for i in range(3000)) + "g();" + "}" * 3000
    started = time.perf_counter()

    chained = _extract("chain.ts", chain)
    deep = _extract("deep.ts", nested)

    assert len(chained.calls) == 20001
    assert len(deep.symbols) == 3001
    # Linear in the chain length this takes ~0.3 s; a query that holds a match open for every link takes ~5 s.
    assert time.perf_counter() - started < 3.0
