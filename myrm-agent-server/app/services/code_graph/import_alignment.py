"""Alignment of the name given to ``importers`` with the import texts stored in the index.

[INPUT]
- 无内部依赖（仅标准库 dataclasses、sys）

[OUTPUT]
- MAX_SCOPE_MODULES: how many same-named modules one query searches
- ImportScope: the import texts that belong to a query and the indexed modules the query can mean
- importer_scope: builds the scope from the query and the indexed Python module names

[POS]
查询层纯函数：importers 查询名与索引里导入文本的对齐。索引里的模块名由文件路径得到（``src.pkg.util``），源码里的导入文本以导入根为起点（``pkg.util``），
相对导入又被抽取器还原成路径形式；这里按点边界把两种写法对齐。重名时返回全部候选，不合并也不猜。
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

# A bare name such as ``models`` can fit hundreds of modules; every searched module adds a range to the SQL query.
MAX_SCOPE_MODULES = 50

_PACKAGE_INIT = ".__init__"


@dataclass(frozen=True)
class ImportScope:
    """What an ``importers`` query asks for.

    ``prefixes``: an import text belongs to the query when it equals a prefix or lies inside it (``prefix.name``).
    ``modules``: the indexed modules the query can mean, empty when it names none (a third-party module, a class
    of an unindexed file); more than one means the name is ambiguous and the answer may mix their importers.
    """

    prefixes: tuple[str, ...]
    modules: tuple[str, ...]


def _canonical(module_name: str) -> str:
    """The name a package is imported by: the module of ``pkg/__init__.py`` is ``pkg``."""
    return module_name.removesuffix(_PACKAGE_INIT)


def _matching(modules: Sequence[str], dotted: str) -> list[str]:
    """Modules that are ``dotted`` or end with it at a dot boundary (``src.pkg.util`` ends with ``pkg.util``)."""
    tail = f".{dotted}"
    return [module for module in modules if module == dotted or module.endswith(tail)]


def _aliases(module: str, modules: Sequence[str]) -> set[str]:
    """The names source code imports ``module`` by when it sits below a ``src`` directory (``src.pkg.util`` is ``pkg.util``).

    ``src`` is the one import root that can be told from the path alone; cutting at any other directory would also take
    the imports of third-party packages that share a name (a local ``app/redis.py`` must not own every ``import redis``).
    A name counts only when no other module fits it and its first part is not a standard library module: otherwise
    ``import json`` would be taken for an import of ``src.json``.
    """
    parts = module.split(".")
    aliases = set()
    for root, part in enumerate(parts[:-1]):
        alias_parts = parts[root + 1 :]
        if part == "src" and alias_parts[0] not in sys.stdlib_module_names:
            alias = ".".join(alias_parts)
            if len(_matching(modules, alias)) == 1:
                aliases.add(alias)
    return aliases


def importer_scope(query: str, module_names: Iterable[str]) -> ImportScope:
    """Resolve ``query`` (a module, or a name inside one) against the indexed Python module names.

    The longest leading part of the query that names a module is that module; the rest is a name inside it. The
    query text itself always stays in the scope, so imports written exactly as asked are found in any layout.
    """
    modules = sorted({_canonical(name) for name in module_names})
    parts = query.split(".")
    for end in range(len(parts), 0, -1):
        found = _matching(modules, ".".join(parts[:end]))
        if not found:
            continue
        names = set(found[:MAX_SCOPE_MODULES])
        if len(found) == 1:
            names |= _aliases(found[0], modules)
        inside = "".join(f".{part}" for part in parts[end:])
        return ImportScope(
            prefixes=tuple(sorted({query, *(name + inside for name in names)})),
            modules=tuple(found),
        )
    return ImportScope(prefixes=(query,), modules=())
