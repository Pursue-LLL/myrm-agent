"""A provider that answers 402 has no credit left: its credential leaves the rotation, whatever words the body holds.

The failure reaches the chain wrapped by ``WebSearcher``, with the status in the wrapper's context rather than on the
exception, so the verdict has to be read from there. Only the provider's HTTP round trip is faked: the adapters, the retry
loop, the wrapping and the chain are the production code. The controls are answers that must never switch a credential
off for the long depleted cooldown.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

import pytest

from myrm_agent_harness.toolkits.web_search.providers.chain import (
    ProviderQuotaStatus,
    ProviderQuotaTracker,
    quota_tracker_key,
    search_provider_chain,
)
from myrm_agent_harness.toolkits.web_search.providers.rest_search import RestSearch, SearchHTTPError
from myrm_agent_harness.toolkits.web_search.providers.search_adapters import SearchRequest
from myrm_agent_harness.toolkits.web_search.providers.web_searcher import SearchServiceConfig

_SEARCHES = 3

_RESULTS: dict[str, Mapping[str, object]] = {
    "brave": {"web": {"results": [{"title": "t", "url": "https://example.org/a", "description": "d"}]}},
    "tavily": {"results": [{"title": "t", "url": "https://example.org/a", "content": "d"}]},
}

# A 402 body with none of the words the text classifier looks for: only the status says the account is out of credit.
_EXA_NO_MORE_CREDITS = {"requestId": "r", "error": "The account has no remaining credits.", "tag": "NO_MORE_CREDITS"}
_BRAVE_PER_SECOND_LIMIT = {
    "type": "ErrorResponse",
    "error": {
        "status": 429,
        "detail": "Request rate limit exceeded for plan",
        "meta": {"plan": "Free", "rate_limit": 1, "rate_current": 1, "quota_limit": 2000, "quota_current": 342},
        "code": "RATE_LIMITED",
    },
}
_BAD_GATEWAY_PAGE = "<html>Bad gateway cf-ray: 8a1c429d7e5f6a01</html>"
_REJECTED_CREDENTIAL = {"detail": {"error": "Unauthorized: missing or invalid API key."}}


@dataclass
class _Outcome:
    """What the credential of the failing provider went through over ``_SEARCHES`` consecutive searches."""

    state: ProviderQuotaStatus
    contacts: int
    winners: list[str]


async def _search_with_failing_head(
    monkeypatch: pytest.MonkeyPatch, failing: str, status: int, body: object
) -> _Outcome:
    """Search ``_SEARCHES`` times through ``[failing provider, healthy provider]``; the head answers ``status``."""
    healthy = "tavily" if failing == "brave" else "brave"
    text = body if isinstance(body, str) else json.dumps(body)
    contacted: list[str] = []

    async def fake_send(self: RestSearch, request: SearchRequest) -> Mapping[str, object]:
        contacted.append(self.search_provider)
        if self.search_provider == failing:
            raise SearchHTTPError(self.search_provider, status, text)
        return _RESULTS[self.search_provider]

    monkeypatch.setattr(RestSearch, "_send", fake_send)

    head = SearchServiceConfig(search_service=failing, api_key="head-key", search_max_retries=0)
    tail = SearchServiceConfig(search_service=healthy, api_key="tail-key", search_max_retries=0)
    tracker = ProviderQuotaTracker()
    winners = [
        (await search_provider_chain([head, tail], f"query {index}", 3, quota_tracker=tracker))[1]
        for index in range(_SEARCHES)
    ]
    state, _reason = tracker.get_status(quota_tracker_key(head))
    return _Outcome(state=state, contacts=contacted.count(failing), winners=winners)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failing", "body"),
    [
        pytest.param("exa_ai", _EXA_NO_MORE_CREDITS, id="exa-no-more-credits"),
        pytest.param("tavily", {}, id="empty-body"),
    ],
)
async def test_a_payment_required_answer_takes_the_credential_out_of_rotation(
    monkeypatch: pytest.MonkeyPatch, failing: str, body: object
) -> None:
    outcome = await _search_with_failing_head(monkeypatch, failing, 402, body)

    assert outcome.state is ProviderQuotaStatus.DEPLETED
    assert outcome.contacts == 1  # the first search finds out; the next ones do not ask again
    assert outcome.winners == ["brave"] * _SEARCHES


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failing", "status", "body"),
    [
        pytest.param("brave", 429, _BRAVE_PER_SECOND_LIMIT, id="per-second-limit-naming-the-monthly-quota"),
        pytest.param("tavily", 502, _BAD_GATEWAY_PAGE, id="bad-gateway-page"),
        pytest.param("tavily", 401, _REJECTED_CREDENTIAL, id="rejected-credential"),
    ],
)
async def test_an_answer_that_is_not_an_account_verdict_does_not_deplete_the_credential(
    monkeypatch: pytest.MonkeyPatch, failing: str, status: int, body: object
) -> None:
    outcome = await _search_with_failing_head(monkeypatch, failing, status, body)

    assert outcome.state is not ProviderQuotaStatus.DEPLETED
    assert outcome.winners == ["tavily" if failing == "brave" else "brave"] * _SEARCHES
