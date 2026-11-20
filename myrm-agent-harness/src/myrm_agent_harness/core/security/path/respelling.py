"""Respelling: the on-disk name of a path the model typed with quotes, compatibility characters or decomposed accents.

``file_read_tool`` opens the respelling when the typed path names nothing. The lookup probes the place the tools
open (``typed_path.spelled_path``), judges a network spelling on its text before any filesystem call, and never lands
on a device or on a credential file the typed text does not name. The permission engine judges the typed spelling and
the respelling alike, so what the read opens is always a file some verdict has seen.

[INPUT]
- path.filesystem::is_blocked_device_path, is_network_or_nt_path (POS: Generic filesystem path safety — no product protection policy)
- path.rules::is_sensitive_file (POS: Protected-path policy)
- path.typed_path::spelled_path (POS: The one definition of which file a tool opens for the text it was given)

[OUTPUT]
- generate_unicode_path_candidates: the distinct spellings of a path over 7 normalization stages, in stage order
- find_existing_unicode_path: the spelling a read opens in place of a typed one that names nothing, or None

[POS]
Respelling of the path security domain: finds the file a model meant when its typed spelling differs from the disk.
"""

from __future__ import annotations

import os
import re
import unicodedata

from myrm_agent_harness.core.security.path.filesystem import is_blocked_device_path, is_network_or_nt_path
from myrm_agent_harness.core.security.path.rules import is_sensitive_file
from myrm_agent_harness.core.security.path.typed_path import spelled_path

__all__ = ("find_existing_unicode_path", "generate_unicode_path_candidates")

# The lookbehind lets the trailing run start only where it begins: without it every position inside a long run
# retries the whole run, which is quadratic in a length the model controls.
_QUOTE_STRIP_RE = re.compile(r"^[\s\"'“”‘’`]+|(?<![\s\"'“”‘’`])[\s\"'“”‘’`]+$")
_SLASH_COLLAPSE_RE = re.compile(r"[\\/]+")

_PATH_UNICODE_MAP: dict[str, str] = {
    "\u2018": "'",  # left single quote
    "\u2019": "'",  # right single quote
    "\u201c": '"',  # left double quote
    "\u201d": '"',  # right double quote
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
    "\u2026": "...",  # ellipsis
    "\u00a0": " ",  # non-breaking space
    "\u200b": "",  # zero-width space
    "\u200c": "",  # zero-width non-joiner
    "\u200d": "",  # zero-width joiner
    "\ufeff": "",  # BOM / zero-width no-break space
    "\uff0f": "/",  # fullwidth solidus
    "\uff3c": "/",  # fullwidth reverse solidus
}

_PATH_UNICODE_RE = re.compile("|".join(re.escape(k) for k in _PATH_UNICODE_MAP))


def generate_unicode_path_candidates(raw_path: str) -> list[str]:
    """Generate up to 7 distinct candidate path variants via Unicode normalization chains.

    Chain stages:
    0. Surrounding quotes & whitespace stripped
    1. NFC normalization (Canonical Decomposition followed by Canonical Composition)
    2. NFD normalization (Canonical Decomposition - macOS APFS/HFS+ native form)
    3. NFKC normalization (Compatibility Decomposition followed by Canonical Composition)
    4. NFKD normalization (Compatibility Decomposition)
    5. Custom character substitution (curly quotes, NBSP, zero-width spaces, dashes)
    6. NFKC + custom character substitution combined
    7. Slash normalization (collapsing redundant separators)

    Returns a deduplicated list of non-empty candidates preserving stage priority.
    """
    if not raw_path:
        return []

    candidates: list[str] = []
    seen: set[str] = set()

    def _add(cand: str) -> None:
        cand_clean = cand.strip()
        if cand_clean and cand_clean not in seen:
            seen.add(cand_clean)
            candidates.append(cand_clean)

    # Stage 0: Stripped raw
    stage0 = _QUOTE_STRIP_RE.sub("", raw_path)
    _add(stage0)
    _add(raw_path)

    base = stage0 or raw_path

    # Stage 1: NFC
    _add(unicodedata.normalize("NFC", base))

    # Stage 2: NFD
    _add(unicodedata.normalize("NFD", base))

    # Stage 3: NFKC
    _add(unicodedata.normalize("NFKC", base))

    # Stage 4: NFKD
    _add(unicodedata.normalize("NFKD", base))

    # Stage 5: Custom Unicode character mapping
    mapped = _PATH_UNICODE_RE.sub(lambda m: _PATH_UNICODE_MAP[m.group()], base)
    _add(mapped)

    # Stage 6: Combined mapping + NFKC/NFC
    _add(unicodedata.normalize("NFC", mapped))
    _add(unicodedata.normalize("NFKC", mapped))

    # Stage 7: Collapsed slashes
    for c in list(candidates):
        collapsed = _SLASH_COLLAPSE_RE.sub("/", c)
        _add(collapsed)

    return candidates


def find_existing_unicode_path(target_path: str, base_dir: str | None = None) -> str | None:
    """The respelling of *target_path* that a read opens in its place, or ``None`` when it opens the typed one.

    The typed spelling wins whenever it exists. Otherwise the first candidate that exists where the tools open it
    (below *base_dir* for a relative name, the user's home for a bare ``~``) is returned, unless it is a device
    or a credential file by name that the typed text does not name: the credential labelling of a read and the ask
    of the permission engine key to the typed text, so a respelling must not turn it into a file they never saw.

    A network or NT-namespace spelling is refused on its text, the typed one and each candidate, before the first
    ``exists`` call: asking about such a path on Windows connects to the host it names.
    """
    if not target_path or is_network_or_nt_path(target_path) or os.path.exists(spelled_path(target_path, base_dir)):
        return None

    for candidate in generate_unicode_path_candidates(target_path):
        if candidate == target_path or is_network_or_nt_path(candidate):
            continue
        place = spelled_path(candidate, base_dir)
        if not os.path.exists(place):
            continue
        if is_sensitive_file(candidate) and not is_sensitive_file(target_path):
            continue
        if is_blocked_device_path(place):
            continue
        return candidate
    return None
