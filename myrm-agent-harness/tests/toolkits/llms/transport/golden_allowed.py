"""Registry of every intentional difference between the previous client library's requests and the transport's.

[INPUT]
- golden_allowed_defects / _equivalents / _responses (POS: the three sections of the registry)

[OUTPUT]
- RULES: the registry

[POS]
The golden request test fails on any difference that is not listed here, so replacing the client library cannot
silently change what reaches a provider. Each rule states why the difference is wanted: either the previous request
was invalid or unsafe for the provider (a defect), or the transport sends the same meaning in another valid form.
A rule that no longer matches anything fails the test too, so this list never keeps stale entries.
"""

from __future__ import annotations

from .golden_allowed_defects import DEFECT_RULES
from .golden_allowed_equivalents import EQUIVALENT_RULES
from .golden_allowed_responses import RESPONSES_RULES
from .golden_allowed_types import AllowedDiff

RULES: tuple[AllowedDiff, ...] = (*DEFECT_RULES, *EQUIVALENT_RULES, *RESPONSES_RULES)
