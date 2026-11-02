"""Tests for how an ``importers`` query is aligned with the indexed Python module names.

[INPUT]
- app.services.code_graph.import_alignment (POS: query-time pure functions that align a query with import texts)

[OUTPUT]
- pytest suite: a query names a module in either spelling (path-style or as written in source) in flat and src
  layouts, a name inside a module keeps its tail, packages are named without ``__init__`` and a whole ``__init__``
  part of a query never takes part in the matching (the query text itself is still searched), only whole dot-separated
  parts and exact case match, only a ``src`` directory is an import root and standard library names are never taken
  for an alias, and a shared name returns every candidate (capped) instead of choosing one.

[POS]
myrm-agent-server/tests/services/code_graph/test_code_graph_import_alignment.py
"""

from __future__ import annotations

import pytest

from app.services.code_graph.import_alignment import MAX_SCOPE_MODULES, importer_scope


def test_a_flat_layout_module_is_searched_under_its_own_name() -> None:
    scope = importer_scope("pkg.util", ["pkg.util", "pkg.other", "app.main"])

    assert (scope.prefixes, scope.modules) == (("pkg.util",), ("pkg.util",))


def test_a_src_layout_module_is_found_by_the_name_source_code_imports_it_by() -> None:
    scope = importer_scope("pkg.util", ["src.pkg.util", "src.pkg.other"])

    assert (scope.prefixes, scope.modules) == (("pkg.util", "src.pkg.util"), ("src.pkg.util",))


def test_a_src_layout_module_is_found_by_the_name_the_index_gives_it() -> None:
    scope = importer_scope("src.pkg.util", ["src.pkg.util", "src.pkg.other"])

    assert (scope.prefixes, scope.modules) == (("pkg.util", "src.pkg.util"), ("src.pkg.util",))


def test_a_name_inside_a_module_keeps_its_tail_under_every_spelling() -> None:
    scope = importer_scope("pkg.util.Helper.run", ["src.pkg.util"])

    assert scope.prefixes == ("pkg.util.Helper.run", "src.pkg.util.Helper.run")
    assert scope.modules == ("src.pkg.util",)


def test_the_longest_leading_part_that_names_a_module_decides_which_module_is_meant() -> None:
    scope = importer_scope("pkg.util.sub.Thing", ["src.pkg.util", "src.pkg.util.sub"])

    assert scope.modules == ("src.pkg.util.sub",)
    assert "src.pkg.util.sub.Thing" in scope.prefixes


def test_a_package_is_named_without_its_init_module() -> None:
    scope = importer_scope("pkg", ["src.pkg.__init__", "src.pkg.util"])

    assert (scope.prefixes, scope.modules) == (("pkg", "src.pkg"), ("src.pkg",))


@pytest.mark.parametrize(
    ("query", "prefixes"),
    [
        ("pkg.__init__", ("pkg", "pkg.__init__")),
        ("pkg.__init__.Thing", ("pkg.Thing", "pkg.__init__.Thing")),
    ],
)
def test_an_init_part_of_the_query_does_not_take_part_in_the_matching(query: str, prefixes: tuple[str, ...]) -> None:
    scope = importer_scope(query, ["pkg.__init__", "pkg.util"])

    assert (scope.prefixes, scope.modules) == (prefixes, ("pkg",))


def test_a_src_layout_package_is_found_by_the_name_resolve_gives_its_symbols() -> None:
    scope = importer_scope("src.pkg.__init__.Thing", ["src.pkg.__init__", "src.pkg.util"])

    assert scope.modules == ("src.pkg",)
    assert scope.prefixes == ("pkg.Thing", "src.pkg.Thing", "src.pkg.__init__.Thing")


def test_a_query_made_of_init_alone_is_searched_as_written() -> None:
    scope = importer_scope("__init__", ["pkg.__init__"])

    assert (scope.prefixes, scope.modules) == (("__init__",), ())


def test_an_init_method_asks_for_the_importers_of_its_class() -> None:
    scope = importer_scope("pkg.mod.Foo.__init__", ["pkg.mod"])

    assert scope.prefixes == ("pkg.mod.Foo", "pkg.mod.Foo.__init__")


def test_a_name_that_matches_no_indexed_module_is_searched_as_written() -> None:
    assert importer_scope("requests.adapters", ["pkg.util"]).prefixes == ("requests.adapters",)
    assert importer_scope("requests.adapters", ["pkg.util"]).modules == ()


def test_only_whole_dot_separated_parts_match() -> None:
    assert importer_scope("util", ["pkg.myutil"]).modules == ()
    assert importer_scope("pkg.uti", ["pkg.util"]).modules == ()


def test_names_are_case_sensitive() -> None:
    assert importer_scope("Pkg.util", ["pkg.util"]).modules == ()


def test_only_a_src_directory_counts_as_an_import_root() -> None:
    scope = importer_scope("app.services.redis", ["app.services.redis"])

    assert scope.prefixes == ("app.services.redis",)


def test_a_src_directory_below_the_top_is_an_import_root_too() -> None:
    scope = importer_scope("packages.core.src.core_pkg.util", ["packages.core.src.core_pkg.util"])

    assert scope.prefixes == ("core_pkg.util", "packages.core.src.core_pkg.util")


def test_a_standard_library_name_is_never_taken_for_an_alias_of_a_src_layout_module() -> None:
    scope = importer_scope("src.json", ["src.json"])

    assert scope.prefixes == ("src.json",)


def test_a_name_below_src_that_fits_several_modules_is_not_used_as_an_alias() -> None:
    modules = ["packages.a.src.pkg.models", "packages.b.src.pkg.models"]

    scope = importer_scope("packages.a.src.pkg.models", modules)

    assert (scope.prefixes, scope.modules) == (("packages.a.src.pkg.models",), ("packages.a.src.pkg.models",))


def test_a_name_shared_by_several_modules_returns_every_candidate() -> None:
    scope = importer_scope("models", ["a.models", "b.models", "c.other"])

    assert scope.modules == ("a.models", "b.models")
    assert scope.prefixes == ("a.models", "b.models", "models")


def test_a_name_shared_by_many_modules_searches_only_the_first_ones_but_reports_all() -> None:
    names = [f"pkg{index:03d}.models" for index in range(MAX_SCOPE_MODULES + 10)]

    scope = importer_scope("models", names)

    assert len(scope.modules) == MAX_SCOPE_MODULES + 10
    assert set(scope.prefixes) == {"models", *names[:MAX_SCOPE_MODULES]}
