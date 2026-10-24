"""Lazy custom-provider registration.

[INPUT]
- myrm_agent_harness.toolkits.llms.providers::ensure_providers_registered
- myrm_agent_harness.toolkits.llms.core.llm

[OUTPUT]
- Regression coverage for keeping litellm out of the HTTP-server import path
  while still registering custom providers before the first model is built.

[POS]
Harness LLM tests. A future eager import of a provider module would re-add ~3.7 s
to every server start, so this gate asserts both the lazy import and the registration.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from myrm_agent_harness.toolkits.llms.providers import ensure_providers_registered

_HARNESS_ROOT = Path(__file__).resolve().parents[3]


def test_importing_the_llm_core_does_not_load_litellm() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import myrm_agent_harness.toolkits.llms.core.llm; "
            "print('litellm' in sys.modules)",
        ],
        cwd=_HARNESS_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False"


def test_registration_is_idempotent_and_registers_both_providers() -> None:
    import litellm

    ensure_providers_registered()
    ensure_providers_registered()

    registered = {entry.get("provider") for entry in litellm.custom_provider_map}
    assert {"minimax_image", "yunshu"} <= registered
