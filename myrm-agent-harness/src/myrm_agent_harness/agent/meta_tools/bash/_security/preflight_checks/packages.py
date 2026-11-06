"""安装包存在性校验（防 AI 幻觉包名）。

[POS]
bash 预检子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import asyncio
import logging
import re
import urllib.error
import urllib.request

from myrm_agent_harness.core.security.redact import command_preview

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Install Package Registry Verification (Anti-Slopsquatting)
# ---------------------------------------------------------------------------

_PIP_INSTALL_RE = re.compile(
    r"(?:pip3?|python3?\s+-m\s+pip|uv\s+pip)\s+install\s+(.+?)(?:\s*(?:&&|;|\||2>&1|1>&2|2>|1>|>|<)\s*|$)",
    re.IGNORECASE,
)
_UV_ADD_RE = re.compile(
    r"uv\s+add\s+(.+?)(?:\s*(?:&&|;|\|)\s*|$)",
    re.IGNORECASE,
)
_NPM_INSTALL_RE = re.compile(
    r"(?:npm|pnpm)\s+(?:install|i|add)\s+(.+?)(?:\s*(?:&&|;|\|)\s*|$)",
    re.IGNORECASE,
)
_YARN_ADD_RE = re.compile(
    r"yarn\s+add\s+(.+?)(?:\s*(?:&&|;|\|)\s*|$)",
    re.IGNORECASE,
)
_BUN_ADD_RE = re.compile(
    r"bun\s+(?:add|install)\s+(.+?)(?:\s*(?:&&|;|\|)\s*|$)",
    re.IGNORECASE,
)

_PRIVATE_REGISTRY_RE = re.compile(
    r"--(?:index-url|extra-index-url|registry)\b",
    re.IGNORECASE,
)

_LOCAL_PACKAGE_PREFIXES = ("./", "../", "file://", "git+", "/")
_REQUIREMENTS_FILE_RE = re.compile(r"^.+\.(?:txt|cfg|toml|in)$")

_PIP_FLAGS_WITH_VALUE: frozenset[str] = frozenset(
    {
        "-r",
        "--requirement",
        "-c",
        "--constraint",
        "-e",
        "--editable",
        "-f",
        "--find-links",
        "-i",
        "--index-url",
        "--extra-index-url",
        "--no-index",
        "--prefix",
        "--root",
        "--target",
        "-t",
    }
)

_PIP_VERSION_SPEC_RE = re.compile(r"[>=<~!;\[]")
_NPM_VERSION_SPEC_RE = re.compile(r"@(?![\w-]+/)")

_PYPI_NORMALIZE_RE = re.compile(r"[-_.]+")

_PROBE_TIMEOUT_S = 5

_verified_packages: set[str] = set()


def _normalize_pypi_name(name: str) -> str:
    """PEP 503 normalization: underscores, dots, hyphens all become ``-``."""
    return _PYPI_NORMALIZE_RE.sub("-", name).lower()


def _strip_python_version_spec(token: str) -> str:
    parts = _PIP_VERSION_SPEC_RE.split(token, maxsplit=1)
    return parts[0]


def _strip_npm_version_spec(token: str) -> str:
    if token.startswith("@") and "/" in token:
        scope_end = token.index("/") + 1
        rest = token[scope_end:]
        parts = _NPM_VERSION_SPEC_RE.split(rest, maxsplit=1)
        return token[:scope_end] + parts[0]
    parts = _NPM_VERSION_SPEC_RE.split(token, maxsplit=1)
    return parts[0]


def _extract_pip_packages(args_str: str) -> list[str]:
    """Extract package names from pip install arguments."""
    packages: list[str] = []
    skip_next = False
    tokens = args_str.split()
    for i, token in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue
        token = token.strip("'\"")
        if token.startswith("-"):
            if token in _PIP_FLAGS_WITH_VALUE:
                skip_next = i + 1 < len(tokens)
            continue
        if token in ("2>&1", "1>&2", "2>", "1>", ">", "<", "|", "||", "&&", ";"):
            break
        if any(token.startswith(prefix) for prefix in _LOCAL_PACKAGE_PREFIXES):
            continue
        if _REQUIREMENTS_FILE_RE.match(token):
            continue
        name = _strip_python_version_spec(token)
        if name:
            packages.append(name)
    return packages


def _extract_npm_packages(args_str: str) -> list[str]:
    """Extract package names from npm/pnpm/yarn/bun install arguments."""
    packages: list[str] = []
    for token in args_str.split():
        token = token.strip("'\"")
        if token.startswith("-"):
            continue
        if any(token.startswith(prefix) for prefix in _LOCAL_PACKAGE_PREFIXES):
            continue
        name = _strip_npm_version_spec(token)
        if name:
            packages.append(name)
    return packages


async def _probe_registry(package: str, url: str, cache_key: str) -> tuple[str, bool]:
    """HEAD-probe a registry URL. Returns (package_name, exists).

    Network errors gracefully fallback to ``exists=True`` so the install is not blocked.
    """
    if cache_key in _verified_packages:
        return package, True

    try:
        loop = asyncio.get_running_loop()
        # S310 cannot fire: both callers pass an f-string whose scheme is the
        # literal "https://" prefix, so no caller-controlled scheme reaches urlopen.
        request = urllib.request.Request(  # noqa: S310
            url, headers={"User-Agent": "myrm-slopcheck"}, method="HEAD"
        )
        response = await loop.run_in_executor(
            None,
            lambda: urllib.request.urlopen(  # noqa: S310
                request, timeout=_PROBE_TIMEOUT_S
            ),
        )
        exists = response.status == 200
    except urllib.error.HTTPError as exc:
        exists = exc.code != 404
    except (urllib.error.URLError, TimeoutError, OSError):
        return package, True

    if exists:
        _verified_packages.add(cache_key)
    return package, exists


def _probe_pypi(package: str) -> asyncio.Task[tuple[str, bool]]:
    normalized = _normalize_pypi_name(package)
    return asyncio.create_task(
        _probe_registry(package, f"https://pypi.org/pypi/{normalized}/json", f"pypi:{normalized}")
    )


def _probe_npm(package: str) -> asyncio.Task[tuple[str, bool]]:
    return asyncio.create_task(_probe_registry(package, f"https://registry.npmjs.org/{package}", f"npm:{package}"))


async def check_install_packages(command: str) -> None:
    """Verify that packages in install commands exist on public registries.

    Blocks commands that attempt to install non-existent packages, preventing
    both wasted time on failed installs and potential slopsquatting attacks
    where LLM-hallucinated package names may be registered with malicious payloads.

    Raises:
        ToolError: If any package does not exist on its respective registry.
    """
    if _PRIVATE_REGISTRY_RE.search(command):
        return

    command = command.replace("\\\n", " ")

    pip_packages: list[str] = []
    npm_packages: list[str] = []

    for match in _PIP_INSTALL_RE.finditer(command):
        pip_packages.extend(_extract_pip_packages(match.group(1)))
    for match in _UV_ADD_RE.finditer(command):
        pip_packages.extend(_extract_pip_packages(match.group(1)))

    for match in _NPM_INSTALL_RE.finditer(command):
        npm_packages.extend(_extract_npm_packages(match.group(1)))
    for match in _YARN_ADD_RE.finditer(command):
        npm_packages.extend(_extract_npm_packages(match.group(1)))
    for match in _BUN_ADD_RE.finditer(command):
        npm_packages.extend(_extract_npm_packages(match.group(1)))

    if not pip_packages and not npm_packages:
        return

    tasks: list[asyncio.Task[tuple[str, bool]]] = []
    for pkg in pip_packages:
        tasks.append(_probe_pypi(pkg))
    for pkg in npm_packages:
        tasks.append(_probe_npm(pkg))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    missing: list[tuple[str, str]] = []
    for result in results:
        if isinstance(result, BaseException):
            continue
        name, exists = result
        if not exists:
            registry = "PyPI" if name in pip_packages else "npm"
            missing.append((name, registry))

    if missing:
        from myrm_agent_harness.utils.errors import ToolError

        details = "; ".join(f"'{name}' not found on {reg}" for name, reg in missing)
        logger.warning("Slopcheck blocked install: %s (command: %s)", details, command_preview(command, 120))
        raise ToolError(
            f"Package verification failed: {details}. "
            "Please verify the package name(s) — AI models sometimes hallucinate non-existent packages.",
            user_hint=f"The following packages do not exist: {details}. "
            "Double-check the package name or search the registry for the correct one.",
        )
