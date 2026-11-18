"""Entropy scan: random-looking tokens are candidates; hex digests, base64 blobs, references and non-ASCII are not."""

from __future__ import annotations

import pytest

from myrm_agent_harness.core.security.detection.entropy_scan import (
    find_high_entropy,
    redact_high_entropy,
    shannon_entropy,
)

RANDOM_TOKEN = "aB3xK9mW2pQ7vL4nR8sT1yU6hD0jF5cG"


def _tokens(text: str, already_matched: frozenset[str] = frozenset()) -> list[str]:
    return [text[start:end] for start, end in find_high_entropy(text, set(already_matched))]


def _mask(token: str) -> str:
    return f"<{len(token)}>"


class TestShannonEntropy:
    def test_empty_string_has_no_entropy(self) -> None:
        assert shannon_entropy("") == 0.0

    def test_single_repeated_character_has_no_entropy(self) -> None:
        assert shannon_entropy("aaaa") == 0.0

    def test_random_string_is_high(self) -> None:
        assert shannon_entropy("aB3xK9mW2pQ7vL4nR8sT1yU6") > 4.0


class TestFindHighEntropy:
    def test_random_token_is_reported_with_its_span(self) -> None:
        text = f"Found: {RANDOM_TOKEN}"

        assert find_high_entropy(text, set()) == [(7, 7 + len(RANDOM_TOKEN))]

    @pytest.mark.parametrize(
        "text",
        [
            f"see https://example.com/download/{RANDOM_TOKEN}",
            "id 123e4567-e89b-12d3-a456-426614174000 done",
            "sha " + "ab12" * 12,
            "blob QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo0MTIz+/=",
            "path /var/lib/aB3xK9mW2pQ7vL4nR8sT1yU6hD0jF5cG/data",
            "raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)",
            "令牌aB3xK9mW2pQ7vL4nR8sT1yU6hD0jF5cG",
            "letters only: abcdefghijklmnopqrstuvwxyzabcdefgh",
            "pod payments-api-7d9f8b6c5-x4k2p is CrashLoopBackOff",
            "NAME kube-prometheus-stack-operator-6f7d9c5b8-zt4lq 1/1 Running",
            "pod/payments-api-7d9f8b6c5-x4k2p condition met",
            "replicaset.apps/kube-prometheus-stack-operator-6f7d9c5b8 scaled",
            "payments-api-7d9f8b6c5-x4k2p.prod unreachable",
        ],
        ids=[
            "url",
            "uuid",
            "hex-digest",
            "base64-blob",
            "file-path",
            "reference",
            "non-ascii",
            "no-digit",
            "k8s-pod-name",
            "k8s-pod-listing",
            "k8s-pod-path",
            "k8s-replicaset-path",
            "k8s-pod-domain",
        ],
    )
    def test_text_that_is_not_a_secret_is_ignored(self, text: str) -> None:
        assert _tokens(text) == []

    def test_credential_that_borrows_a_pod_name_prefix_is_still_reported(self) -> None:
        token = "payments-api-prod-9f3k2x7m4q8w1zb7"
        assert _tokens(f"Found: {token}") == [token]

    def test_token_already_matched_by_another_tier_is_skipped(self) -> None:
        assert _tokens(f"Found: {RANDOM_TOKEN}", frozenset({f"prefix_{RANDOM_TOKEN}_suffix"})) == []

    def test_every_occurrence_of_a_token_is_reported(self) -> None:
        assert _tokens(f"a {RANDOM_TOKEN} b {RANDOM_TOKEN}") == [RANDOM_TOKEN, RANDOM_TOKEN]

    def test_a_token_after_skipped_text_keeps_its_offsets(self) -> None:
        text = f"see https://example.com/a/b and /var/lib/x/y then {RANDOM_TOKEN}"

        assert find_high_entropy(text, set()) == [(text.index(RANDOM_TOKEN), len(text))]


class TestRedactHighEntropy:
    def test_the_token_is_replaced_and_the_text_around_it_is_kept(self) -> None:
        assert redact_high_entropy(f"key ({RANDOM_TOKEN}), next", set(), _mask) == "key (<32>), next"

    def test_a_token_that_also_stands_in_a_path_is_replaced_where_it_stands_alone(self) -> None:
        text = f'{{"log": ".context/{RANDOM_TOKEN}/evicted/out.txt", "id": "{RANDOM_TOKEN}"}}'

        assert redact_high_entropy(text, set(), _mask) == (
            f'{{"log": ".context/{RANDOM_TOKEN}/evicted/out.txt", "id": "<32>"}}'
        )

    def test_every_occurrence_is_replaced(self) -> None:
        assert redact_high_entropy(f"{RANDOM_TOKEN} and {RANDOM_TOKEN}", set(), _mask) == "<32> and <32>"

    def test_text_without_a_token_is_returned_as_it_is(self) -> None:
        text = "nothing random here: /var/lib/x/y and https://example.com/a/b"

        assert redact_high_entropy(text, set(), _mask) is text
