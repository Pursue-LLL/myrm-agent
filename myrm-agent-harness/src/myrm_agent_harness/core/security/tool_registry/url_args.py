"""URL arguments of the network tools: the one place that says which arguments carry URLs.

[INPUT]
- core.security.tool_registry.file_args::coerce_path_list (POS: reads an array argument the way the tools do, a JSON array sent as text included)

[OUTPUT]
- URL_ARG_KEYS: every argument name a network tool receives its URLs under
- url_arg_values: each non-empty URL string among those arguments, passed as a string, a JSON array string or a list

[POS]
Shared by the permission engine (blocklist, per-domain approval and rule targets) so that a URL sent as
``url`` or inside ``urls`` is judged the same way, and so that no judgement reads an argument the tool does
not have: ``web_fetch_tool`` receives its pages in ``urls``, ``browser_navigate_tool`` in ``url``.
"""

from __future__ import annotations

from .file_args import coerce_path_list

URL_ARG_KEYS: tuple[str, ...] = ("url", "urls")


def url_arg_values(args: dict[str, object]) -> list[str]:
    """Every non-empty URL string in the arguments, whether passed as a string, a JSON array string or a list."""
    return [
        item.strip()
        for key in URL_ARG_KEYS
        for item in coerce_path_list(args.get(key)) or ()
        if isinstance(item, str) and item.strip()
    ]
