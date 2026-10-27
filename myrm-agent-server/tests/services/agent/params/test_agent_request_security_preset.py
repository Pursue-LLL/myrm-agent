"""AgentRequest.security_preset field validation."""

import pytest
from pydantic import ValidationError

from app.services.agent.params.models import AgentRequest


class TestAgentRequestSecurityPreset:
    """Verify the Pydantic model accepts/rejects security_preset values."""

    @pytest.mark.parametrize("preset", ["hitl", "accept_edits", "explore", None])
    def test_valid_presets_accepted(self, preset: str | None) -> None:
        req = AgentRequest(message_id="m1", query="test", security_preset=preset)
        assert req.security_preset == preset

    def test_invalid_preset_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentRequest(message_id="m1", query="test", security_preset="invalid")

    def test_default_preset_is_none(self) -> None:
        req = AgentRequest(message_id="m1", query="test")
        assert req.security_preset is None
