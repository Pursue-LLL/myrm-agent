"""GitHub blob page URL to the URL of the file itself.

A ``github.com/<owner>/<repo>/blob/<ref>/<path>`` page is the file wrapped in a large HTML page, so a big source file
overruns the HTTP tier's body ceiling and the model reads only its beginning. The same path under ``/raw/`` is the file
itself: GitHub answers it with a redirect to ``raw.githubusercontent.com`` and resolves a branch name that contains
slashes the way it does for ``blob``, which a rewrite here could not do without guessing where the branch name ends.
The rewrite therefore stays on github.com and leaves the redirect, and every check on it, to the fetch.

[INPUT]
- (none)

[OUTPUT]
- github_blob_to_raw: the ``/raw/`` URL of a github.com blob page; any other URL is returned unchanged

[POS]
Pure URL rewrite. The fetch engine applies it before it builds the cache key, so a blob link and a raw link to the same
file share one cache entry.
"""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

_GITHUB_HOST = "github.com"
# owner, repo, the "blob" marker, ref and at least one path segment
_MIN_SEGMENTS = 5
_MARKER_INDEX = 2


def github_blob_to_raw(url: str) -> str:
    """Return the ``/raw/`` URL of a github.com blob page, ``url`` itself for anything else.

    The query (``?plain=1`` and other display options) and the fragment (``#L10-L20``) belong to the page, not to the
    file, so they are dropped. A path with an empty segment, a port or credentials in the host, or another host
    (including ``www.github.com`` and GitHub Enterprise) is not a blob page this rewrite knows and stays as given.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.netloc.lower() != _GITHUB_HOST:
        return url

    segments = parsed.path.split("/")[1:]
    if len(segments) < _MIN_SEGMENTS or segments[_MARKER_INDEX] != "blob" or not all(segments):
        return url

    segments[_MARKER_INDEX] = "raw"
    return urlunparse((parsed.scheme, parsed.netloc, "/" + "/".join(segments), "", "", ""))
