"""URL arguments of the network tools: the one place that says which arguments carry URLs.

[INPUT]
- core.security.tool_registry.file_args::coerce_path_list (POS: reads an array argument the way the tools do, a JSON array sent as text included)

[OUTPUT]
- URL_ARG_KEYS: every argument name a network tool receives its URLs under
- url_arg_values: each non-empty URL string among those arguments, passed as a string, a JSON array string or a list
- url_host / url_arg_hosts: the host a URL names, and the distinct hosts of every URL a call names

[POS]
Shared by the permission engine (blocklist, per-domain approval and rule targets) and the taint exemption so
that a URL sent as ``url`` or inside ``urls`` is judged the same way, and so that no judgement reads an
argument the tool does not have: ``web_fetch_tool`` receives its pages in ``urls``, ``browser_navigate_tool``
in ``url``.
"""

from __future__ import annotations

from urllib.parse import urlparse

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


def url_host(url: str) -> str:
    """The lowercase host a URL names, without a trailing dot (``evil.com.`` is the host ``evil.com``).

    Reads scheme-prefixed URLs (``http://192.168.1.1/path``) and bare ``host:port`` (``localhost:3000``). A string
    that names no host stands for itself, so a malformed address is neither waved through nor an error.
    """
    if "://" in url:
        try:
            host = urlparse(url).hostname or ""
        except ValueError:
            host = ""
    else:
        host = url.split(":")[0].split("/")[0].lower()
    return host.rstrip(".") or url


def url_arg_hosts(args: dict[str, object]) -> tuple[str, ...]:
    """The distinct hosts of every URL the call names, in order."""
    return tuple(dict.fromkeys(url_host(url) for url in url_arg_values(args)))
