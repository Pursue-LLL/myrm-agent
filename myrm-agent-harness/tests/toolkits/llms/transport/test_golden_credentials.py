"""Golden credentials test: every credential, endpoint and signature is sent as the baseline sent it, except where registered.

[INPUT]
- golden_credentials (POS: scenario matrix recorder)
- golden_credentials_baseline.json (POS: the facts the baseline client library produced for each case)
- golden_credentials_allowed (POS: registry of intended differences)
- golden_catalog.json (POS: the model facts the baseline was recorded with, pinned so a catalog refresh cannot move them)
- golden_compare (POS: comparison engine)

[OUTPUT]
- tests that fail on any unregistered difference, on a registered difference whose facts changed, and on a registry
  entry that matches nothing; the cases of signed Bedrock requests run where botocore is installed

[POS]
Safety net for how a call authenticates and where it goes: Azure keys, versions and Entra tokens, Anthropic keys and
subscription tokens, Bedrock API keys and AWS-signed requests (see ``golden_credentials``). A request that carries a
wrong or an extra credential, goes to another endpoint, or is signed for another region is caught as a changed fact.
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from myrm_agent_harness.toolkits.llms.catalog import store

from .golden_compare import Report, Verdict, compare
from .golden_credentials import SCENARIOS, capture_credentials
from .golden_credentials_allowed import CREDENTIAL_ALLOWED

_BASELINE = Path(__file__).parent / "golden_credentials_baseline.json"
_CATALOG = Path(__file__).parent / "golden_catalog.json"
_HAS_BOTOCORE = importlib.util.find_spec("botocore") is not None
_SIGNED = frozenset(name for name in SCENARIOS if name.startswith("bedrock|sigv4"))


def _runs_here(case: str) -> bool:
    return _HAS_BOTOCORE or case not in _SIGNED


@pytest.fixture(scope="module")
def recorded() -> dict[str, Verdict]:
    document = json.loads(_BASELINE.read_text(encoding="utf-8"))
    return cast(dict[str, Verdict], document["cases"])


@pytest.fixture(scope="module")
def replayed() -> Iterator[dict[str, Verdict]]:
    pinned = json.loads(_CATALOG.read_text(encoding="utf-8"))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(store, "_snapshot", lambda: pinned)
        store._snapshot_by_lowercase.cache_clear()  # derived from the snapshot: must not keep the pinned subset
        yield capture_credentials(patch)
    store._snapshot_by_lowercase.cache_clear()


@pytest.fixture(scope="module")
def report(recorded: dict[str, Verdict], replayed: dict[str, Verdict]) -> Report:
    return compare(
        {case: facts for case, facts in recorded.items() if _runs_here(case)},
        {case: facts for case, facts in replayed.items() if _runs_here(case)},
        CREDENTIAL_ALLOWED,
    )


def test_the_recording_covers_the_matrix(recorded: dict[str, Verdict]) -> None:
    """A case cannot leave the contract unnoticed: the recording and the matrix name the same cases."""
    assert set(recorded) == set(SCENARIOS)


def test_every_credential_is_sent_as_before_or_registered(report: Report) -> None:
    assert not report.unexplained, f"{len(report.unexplained)} cases:\n{report.describe()}"


def test_the_registry_has_no_stale_entries(report: Report) -> None:
    assert not report.stale, f"registered differences that no longer occur: {report.stale}"


@pytest.mark.skipif(not _HAS_BOTOCORE, reason="signing needs botocore")
def test_every_signature_is_valid_by_an_independent_computation(replayed: dict[str, Verdict]) -> None:
    """The verifier rebuilds the canonical request from the bytes sent, so it does not share the signer's bugs."""
    signed = {case: facts for case, facts in replayed.items() if "sigv4.valid" in facts}
    assert set(signed) == _SIGNED - {"bedrock|sigv4_no_credentials"}
    assert {case for case, facts in signed.items() if not facts["sigv4.valid"]} == set()
