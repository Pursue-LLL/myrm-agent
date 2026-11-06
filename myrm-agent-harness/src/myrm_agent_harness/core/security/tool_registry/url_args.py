"""URL arguments of the network tools: the one place that says which arguments carry URLs.

[INPUT]
- core.security.tool_registry.file_args::coerce_path_list (POS: reads an array argument the way the tools do, a JSON array sent as text included)
- utils.url_syntax::parse_outbound_hostname, parse_outbound_url (POS: the canonical spelling of an outbound URL, or why it has none)

[OUTPUT]
- URL_ARG_KEYS: every argument name a network tool receives its URLs under
- url_arg_values: each non-empty URL string among those arguments, passed as a string, a JSON array string or a list
- url_host / url_arg_hosts: the canonical host an outbound URL names, and the distinct hosts of every URL a call names
- url_arg_error: why a URL of the call has no canonical form, or None

[POS]
Shared by the permission engine (blocklist, per-domain approval and rule targets) and the taint exemption so
that a URL sent as ``url`` or inside ``urls`` is judged the same way, and so that no judgement reads an
argument the tool does not have: ``web_fetch_tool`` receives its pages in ``urls``, ``browser_navigate_tool``
in ``url``.
"""

from __future__ import annotations

from myrm_agent_harness.utils.url_syntax import parse_outbound_hostname, parse_outbound_url

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
    """The canonical host an outbound URL names (``evil.com.`` is the host ``evil.com``).

    A string that is not an outbound URL stands for itself: no tool dials it, and a malformed address is neither
    waved through nor an error.
    """
    host, _ = parse_outbound_hostname(url)
    return host or url


def url_arg_hosts(args: dict[str, object]) -> tuple[str, ...]:
    """The distinct hosts of every URL the call names, in order."""
    return tuple(dict.fromkeys(url_host(url) for url in url_arg_values(args)))


def url_arg_error(args: dict[str, object]) -> str | None:
    """Why a URL the call names has no canonical form, or None; a string without ``://`` is no URL to refuse here."""
    for url in url_arg_values(args):
        if "://" in url:
            target, error = parse_outbound_url(url)
            if target is None:
                return error
    return None
