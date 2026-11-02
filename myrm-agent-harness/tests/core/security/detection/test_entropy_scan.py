"""Entropy scan: random-looking tokens are candidates; hex digests, base64 blobs, references and non-ASCII are not."""

from __future__ import annotations

import pytest

from myrm_agent_harness.core.security.detection.entropy_scan import scan_high_entropy, shannon_entropy

RANDOM_TOKEN = "aB3xK9mW2pQ7vL4nR8sT1yU6hD0jF5cG"


class TestShannonEntropy:
    def test_empty_string_has_no_entropy(self) -> None:
        assert shannon_entropy("") == 0.0

    def test_single_repeated_character_has_no_entropy(self) -> None:
        assert shannon_entropy("aaaa") == 0.0

    def test_random_string_is_high(self) -> None:
        assert shannon_entropy("aB3xK9mW2pQ7vL4nR8sT1yU6") > 4.0


class TestScanHighEntropy:
    def test_random_token_is_reported_with_its_pattern_name(self) -> None:
        assert scan_high_entropy(f"Found: {RANDOM_TOKEN}", set()) == [("high_entropy_token", RANDOM_TOKEN)]

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
        assert scan_high_entropy(text, set()) == []

    def test_credential_that_borrows_a_pod_name_prefix_is_still_reported(self) -> None:
        token = "payments-api-prod-9f3k2x7m4q8w1zb7"
        assert scan_high_entropy(f"Found: {token}", set()) == [("high_entropy_token", token)]

    def test_token_already_matched_by_another_tier_is_skipped(self) -> None:
        assert scan_high_entropy(f"Found: {RANDOM_TOKEN}", {f"prefix_{RANDOM_TOKEN}_suffix"}) == []
