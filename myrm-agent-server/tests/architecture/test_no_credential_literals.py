"""Architecture test: the tracked tree holds no real-looking credential.

A credential committed to a public repository is public for good; only revoking it repairs the damage. Three rules
keep one from landing:

1. A string shaped like a provider key (OpenAI-style, Tavily, Voyage, GitHub, AWS, Google, JWT, GitLab, npm, PyPI)
   must look like a fixture, never like a live secret.
2. A literal assigned to an ``api_key``-style name must look like a fixture too; this also covers providers whose
   keys carry no recognizable prefix.
3. Production Python never compares a credential with a string literal: a backdoor that accepts one hard-coded key
   has exactly this shape.

A value looks like a fixture when it carries a placeholder word, repeats a few characters or has low entropy. A test
that needs a realistic shape builds it at call time from ``tests/support/fake_secrets.py`` (server and harness) or
``src/test-utils/fakeSecrets.ts`` (frontend), so no source file holds a contiguous provider-shaped token. Stripe and
Slack shapes in server tests are the job of ``test_no_provider_shaped_secrets_in_tests``.

Findings name file, line, rule and length but never the literal: the CI log of this repository is public. The scan
core also runs against any git revision (``scan_tracked_tree(root, rev)``), which is how the rules were replayed over
history. The test samples are assembled from fragments so this file does not match itself.
"""

from __future__ import annotations

import ast
import hashlib
import math
import re
import subprocess
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PRODUCTION_DIRS = ("myrm-agent-server/app", "myrm-agent-harness/src")
_MAX_REPORTED_HITS = 20
# Minified bundles are not source anyone reviews, and their lines would drown the scan.
_MAX_LINE_LENGTH = 800

_NO_SECRET_BEFORE = "(?<![A-Za-z0-9])"
# Written in the subset that Python's `re` and `git grep -E` both read: the git prefilter reuses this text with the
# leading lookbehind removed, and Python applies the lookbehind afterwards.
_SHAPES: dict[str, str] = {
    "OpenAI-style key": _NO_SECRET_BEFORE + "sk-[A-Za-z0-9_-]{32,}",
    "Tavily key": _NO_SECRET_BEFORE + "tvly-[A-Za-z0-9_-]{20,}",
    "Voyage key": "(?<![A-Za-z0-9_-])pa-[A-Za-z0-9_-]{35,}",
    "GitHub token": _NO_SECRET_BEFORE + "gh[pousr]_[A-Za-z0-9]{36,}",
    "GitHub fine-grained token": _NO_SECRET_BEFORE + "github_pat_[A-Za-z0-9_]{50,}",
    "AWS access key id": _NO_SECRET_BEFORE + "AKIA[0-9A-Z]{16}",
    "Google API key": _NO_SECRET_BEFORE + "AIza[0-9A-Za-z_-]{35}",
    "JWT": "(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{15,}\\.eyJ[A-Za-z0-9_-]{15,}\\.[A-Za-z0-9_-]{10,}",
    "GitLab token": _NO_SECRET_BEFORE + "glpat-[A-Za-z0-9_-]{20,}",
    "npm token": _NO_SECRET_BEFORE + "npm_[A-Za-z0-9]{36}",
    "PyPI token": _NO_SECRET_BEFORE + "pypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{50,}",
}
_QUOTE = "[\"']"
# Group 1 is an optional type annotation (`api_key: str = "..."`); group 2 is the value.
_API_KEY_LITERAL = (
    f"api[_-]?key[A-Za-z0-9_]*{_QUOTE}?([ ]*:[ ]*[A-Za-z_][]A-Za-z0-9_.[| ]*)?[ ]*[:=][ ]*[bu]?{_QUOTE}"
    f"([A-Za-z0-9_+/=.-]{{24,}}){_QUOTE}"
)
_API_KEY_RULE = "api_key literal"
_COMPARISON_RULE = "credential compared with a literal"

_LEADING_LOOKBEHIND = re.compile(r"^\(\?<![^)]*\)")
_SHAPE_REGEXES = {rule: re.compile(pattern) for rule, pattern in _SHAPES.items()}
_API_KEY_REGEX = re.compile(_API_KEY_LITERAL, re.IGNORECASE)

# Words a developer writes into a value to say "not real"; four letters or more keep a random key from containing one.
_FIXTURE_MARKERS = tuple(
    "abcd 1234 0000 xxxx test fake dummy example sample mock invalid placeholder redact secret fixture your".split()
)
_MIN_DISTINCT_CHARS = 10
_MIN_ENTROPY_BITS = 3.2
_COMPARISON_MIN_LITERAL = 16
_CREDENTIAL_NAME = re.compile(r"(?i)(?:^|[_-])(?:api[_-]?key|secret|token|password|passwd|credential)s?$")
_LOOKUP_METHODS = frozenset({"get", "pop", "getenv"})
_COMPARISON_OPERATORS = (ast.Eq, ast.NotEq, ast.In, ast.NotIn)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    length: int

    def __str__(self) -> str:
        return f"{self.path}:{self.line} [{self.rule}, {self.length} chars]"


def _entropy_bits(value: str) -> float:
    return -sum(n / len(value) * math.log2(n / len(value)) for n in Counter(value).values())


def looks_like_fixture(value: str) -> bool:
    lowered = value.lower()
    return (
        any(marker in lowered for marker in _FIXTURE_MARKERS)
        or len(set(value)) < _MIN_DISTINCT_CHARS
        or _entropy_bits(value) < _MIN_ENTROPY_BITS
    )


def _is_unprefixed_secret(value: str) -> bool:
    """Without a provider prefix randomness is the only evidence: a value with no digit is a phrase, a path or a host."""
    has_digit = any(char.isdigit() for char in value)
    is_reference = value.count("/") >= 2 or value.count(".") >= 3
    return has_digit and not is_reference and not looks_like_fixture(value)


def scan_text(text: str) -> list[tuple[str, int]]:
    """Return ``(rule, length)`` for every credential-looking literal in one line of text."""
    hits = [
        (rule, len(match.group(0)))
        for rule, regex in _SHAPE_REGEXES.items()
        for match in regex.finditer(text)
        if not looks_like_fixture(match.group(0))
    ]
    hits += [
        (_API_KEY_RULE, len(match.group(2))) for match in _API_KEY_REGEX.finditer(text) if _is_unprefixed_secret(match.group(2))
    ]
    return hits


def _git_grep(root: Path, patterns: Sequence[str], rev: str | None, *, ignore_case: bool) -> dict[tuple[str, int], str]:
    """Map ``(path, line)`` to the text of every line matching one of the ERE ``patterns`` (status 1 means none)."""
    command = ["git", "grep", "-I", "-n", "-E", *(["-i"] if ignore_case else [])]
    for pattern in patterns:
        command += ["-e", pattern]
    command += [*([rev] if rev else []), "--", ".", ":(exclude)*.lock", ":(exclude)*lock.json"]
    result = subprocess.run(command, cwd=root, capture_output=True, encoding="utf-8", errors="replace", check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"git grep failed with status {result.returncode}: {result.stderr.strip()}")
    lines: dict[tuple[str, int], str] = {}
    for row in result.stdout.splitlines():
        path, number, text = (row.removeprefix(f"{rev}:") if rev else row).split(":", 2)
        lines[(path, int(number))] = text
    return lines


def scan_tracked_tree(root: Path, rev: str | None = None) -> list[Finding]:
    """Apply the literal rules to the tracked text files of the work tree, or of ``rev`` when given."""
    shape_prefilter = [_LEADING_LOOKBEHIND.sub("", pattern) for pattern in _SHAPES.values()]
    candidates = _git_grep(root, shape_prefilter, rev, ignore_case=False)
    candidates |= _git_grep(root, [_API_KEY_LITERAL], rev, ignore_case=True)
    return [
        Finding(path, number, rule, length)
        for (path, number), text in sorted(candidates.items())
        if len(text) <= _MAX_LINE_LENGTH
        for rule, length in scan_text(text)
    ]


def _credential_name(node: ast.expr) -> str | None:
    """Name a credential operand: ``key``, ``obj.key``, ``obj["key"]`` or ``obj.get("key")``."""
    name: str | None = None
    if isinstance(node, ast.Name):
        name = node.id
    elif isinstance(node, ast.Attribute):
        name = node.attr
    elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        name = node.slice.value if isinstance(node.slice.value, str) else None
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in _LOOKUP_METHODS:
        first = node.args[0] if node.args else None
        name = first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None
    return name if name and _CREDENTIAL_NAME.search(name) else None


def _credential_literal_length(node: ast.expr) -> int:
    """Length of the first real-looking string constant in ``node`` (or in a tuple, list or set of them), else 0."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        value = node.value
        return len(value) if len(value) >= _COMPARISON_MIN_LITERAL and not looks_like_fixture(value) else 0
    if isinstance(node, ast.Tuple | ast.List | ast.Set):
        return max((_credential_literal_length(item) for item in node.elts), default=0)
    return 0


def comparisons_with_literals(source: str) -> list[tuple[int, int]]:
    """Return ``(line, literal length)`` for each credential compared with a real-looking string literal."""
    hits: list[tuple[int, int]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left, *node.comparators]
        for operator, left, right in zip(node.ops, operands[:-1], operands[1:], strict=True):
            if not isinstance(operator, _COMPARISON_OPERATORS):
                continue
            for credential, other in ((left, right), (right, left)):
                length = _credential_literal_length(other)
                if length and _credential_name(credential):
                    hits.append((node.lineno, length))
    return hits


def scan_production_comparisons(root: Path) -> list[Finding]:
    return [
        Finding(path.relative_to(root).as_posix(), line, _COMPARISON_RULE, length)
        for relative in _PRODUCTION_DIRS
        for path in sorted((root / relative).rglob("*.py"))
        for line, length in comparisons_with_literals(path.read_text(encoding="utf-8"))
    ]


def _report(findings: Sequence[Finding]) -> str:
    detail = "\n".join(str(finding) for finding in findings[:_MAX_REPORTED_HITS])
    if len(findings) > _MAX_REPORTED_HITS:
        detail += f"\n... and {len(findings) - _MAX_REPORTED_HITS} more"
    return (
        "Tracked files hold credential-looking literals. A real credential must never be committed: revoke it, then "
        "remove the value. A fixture needs an obviously fake value (a word such as 'test' or 'example') or one built "
        "at call time from tests/support/fake_secrets.py (server, harness) or src/test-utils/fakeSecrets.ts "
        "(frontend).\n" + detail
    )


def _body(seed: str, length: int) -> str:
    """Deterministic hex body that is not a fixture, so a sample built from it must be flagged."""
    return (hashlib.sha256(seed.encode()).hexdigest() * 3)[:length]


_SHAPE_SAMPLES = {
    "OpenAI-style key": "sk" + "-" + _body("openai", 48),
    "Tavily key": "tv" + "ly-" + _body("tavily", 32),
    "Voyage key": "p" + "a-" + _body("voyage", 43),
    "GitHub token": "gh" + "p_" + _body("github", 36),
    "GitHub fine-grained token": "github" + "_pat_" + _body("fine-grained", 60),
    "AWS access key id": "AK" + "IA" + _body("aws", 16).upper(),
    "Google API key": "AI" + "za" + _body("google", 35),
    "JWT": "ey" + "J" + _body("jwt-header", 24) + ".ey" + "J" + _body("jwt-payload", 24) + "." + _body("jwt-sig", 24),
    "GitLab token": "gl" + "pat-" + _body("gitlab", 24),
    "npm token": "np" + "m_" + _body("npm", 36),
    "PyPI token": "py" + "pi-AgEIcHlwaS5vcmc" + _body("pypi", 60),
}
_FIXTURE_SAMPLES = {
    "alphabet run": "sk" + "-" + "abcdefghijklmnopqrstuvwxyz0123456789ABCD",
    "placeholder word": "sk" + "-" + "test-" + _body("placeholder", 40),
    "repeated character": "gh" + "p_" + "x" * 36,
    "documented AWS example id": "AK" + "IAIOSFODNN7EXAMPLE",
    "low entropy": "sk" + "-" + "a1" * 24,
    "JWT with a marker": "ey" + "Jtest" + _body("jwt-a", 20) + ".ey" + "J" + _body("jwt-b", 24) + "." + _body("sig", 24),
}
_API_KEY_SAMPLE = _body("api-key-literal", 40)


@pytest.mark.parametrize("rule", _SHAPE_SAMPLES)
def test_shape_rule_flags_a_credential_that_does_not_look_like_a_fixture(rule: str) -> None:
    sample = _SHAPE_SAMPLES[rule]
    assert not looks_like_fixture(sample)
    assert (rule, len(sample)) in scan_text(f'secret_holder = "{sample}"')


@pytest.mark.parametrize("name", _FIXTURE_SAMPLES)
def test_shape_rule_accepts_a_value_that_looks_like_a_fixture(name: str) -> None:
    assert scan_text(f'secret_holder = "{_FIXTURE_SAMPLES[name]}"') == []


@pytest.mark.parametrize(
    "text",
    [
        "see https://example.org/blog/a-long-article-slug-with-many-words-in-the-title",
        "commit " + _body("sha", 40),
        "id 123e4567-e89b-12d3-a456-426614174000",
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhf",
    ],
)
def test_shape_rule_ignores_text_without_a_provider_prefix(text: str) -> None:
    assert scan_text(text) == []


@pytest.mark.parametrize(
    "template",
    ['api_key = "{}"', '"api_key": "{}"', "API_KEY='{}'", 'apiKey: "{}",', 'x-api-key: "{}"', 'api_key: str = "{}"'],
)
def test_api_key_rule_flags_a_literal_in_every_assignment_style(template: str) -> None:
    assert (_API_KEY_RULE, len(_API_KEY_SAMPLE)) in scan_text(template.format(_API_KEY_SAMPLE))


@pytest.mark.parametrize(
    "text",
    [
        'api_key = "short"',
        'api_key = "your-api-key-goes-here-please"',
        'api_key = "' + "a1" * 20 + '"',
        'api_key = "' + "orange-yellow-purple-silver" + '"',
        'api_key = "' + "path/to/the/credential/store/file1" + '"',
        "api_key = os.environ[" + '"API_KEY"]',
        f'token = "{_API_KEY_SAMPLE}"',
    ],
)
def test_api_key_rule_ignores_everything_else(text: str) -> None:
    assert scan_text(text) == []


_COMPARED = _body("compared", 40)


@pytest.mark.parametrize(
    "source",
    [
        f'if request.api_key == "{_COMPARED}":\n    pass\n',
        f'if kwargs.get("api_key") == "{_COMPARED}":\n    pass\n',
        f'allowed = "{_COMPARED}" == settings.access_token\n',
        f'allowed = password in ("short", "{_COMPARED}")\n',
        f'if config["client_secret"] != "{_COMPARED}":\n    pass\n',
        f'if os.getenv("SERVICE_TOKEN") == "{_COMPARED}":\n    pass\n',
    ],
)
def test_comparison_rule_flags_a_credential_checked_against_a_literal(source: str) -> None:
    assert comparisons_with_literals(source) == [(1, len(_COMPARED))]


@pytest.mark.parametrize(
    "source",
    [
        'if token_type == "a-long-token-type-name-here":\n    pass\n',
        'if api_key == "your-api-key-goes-here-please":\n    pass\n',
        'if api_key == "short":\n    pass\n',
        "if api_key == other_key:\n    pass\n",
        'if api_key == os.getenv("SERVICE_API_KEY"):\n    pass\n',
        "if api_key is None:\n    pass\n",
        f'if api_key < "{_COMPARED}":\n    pass\n',
    ],
)
def test_comparison_rule_ignores_everything_else(source: str) -> None:
    assert comparisons_with_literals(source) == []


def test_tracked_files_hold_no_credential_looking_literals() -> None:
    findings = scan_tracked_tree(_REPO_ROOT)
    assert not findings, _report(findings)


def test_production_code_never_compares_a_credential_with_a_literal() -> None:
    findings = scan_production_comparisons(_REPO_ROOT)
    assert not findings, _report(findings)
