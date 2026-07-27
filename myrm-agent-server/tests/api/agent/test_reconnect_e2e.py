"""Legacy path — replaced by ASGI integration tests.

See tests/api/agent/test_reconnect_integration.py
"""

import pytest

pytestmark = pytest.mark.skip(
    reason="Moved to tests/api/agent/test_reconnect_integration.py (ASGI + mock agent)",
)
