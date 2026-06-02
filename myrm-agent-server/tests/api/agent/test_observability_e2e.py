import os
import time
import uuid
from pathlib import Path

import pytest
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.trace_builder import build_trace
from myrm_agent_harness.agent.event_log.types import StructuredEvent

from app.config.settings import settings
from app.services.agent.routing_advisor import analyze_provider_health

_EVENT_LOG_DIR = Path(settings.database.event_log_dir)

@pytest.mark.asyncio
async def test_5min_reactive_degradation():
    """Test the 5-minute reactive degradation logic (routing_advisor)."""
    # Create a unique session ID to avoid collisions
    session_id = f"test_degradation_{uuid.uuid4().hex[:8]}"
    backend = FileEventLogBackend(log_dir=_EVENT_LOG_DIR, session_id=session_id)
    
    current_time = time.time()
    events = []
    
    # Insert 6 failed events for "test_provider" within the last 1 minute
    for i in range(6):
        events.append(
            StructuredEvent(
                sequence=i*2,
                timestamp=current_time - 60,
                event_type="tool_start",
                session_id=session_id,
                data={
                    "tool_name": "test_provider"
                }
            )
        )
        events.append(
            StructuredEvent(
                sequence=i*2 + 1,
                timestamp=current_time - 60 + 1,
                event_type="tool_failure",
                session_id=session_id,
                data={
                    "tool_name": "test_provider",
                    "error": "Timeout",
                    "duration_ms": 1000
                }
            )
        )
    await backend.append(events)
    
    # Analyze health with a 5-minute window
    health = await analyze_provider_health("test_provider", time_window_minutes=5)
    
    assert health["healthy"] is False
    assert health["recommend_fallback"] is True
    assert "High failure rate" in str(health["reason"])

@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
async def test_real_model_ttft_extraction():
    """Test that a real LLM call correctly extracts ttft_ms into ExecutionTrace."""
    message_id = f"test_ttft_{uuid.uuid4().hex[:8]}"
    query = "Reply with 'ttft test' only. Do not use any tools."
    
    from myrm_agent_harness.agent import BaseAgent
    from myrm_agent_harness.toolkits.llms import llm_manager

    from app.core.channel_bridge.config_loader import load_user_configs
    from app.services.agent.params import ModelSelection, _resolve_model_config
    from tests.api.agent.utils import get_model_selection
    
    configs = await load_user_configs()
    model_selection_dict = get_model_selection()
    model_selection = ModelSelection(**model_selection_dict)
    model_cfg = await _resolve_model_config(model_selection, configs.providers_dict or {})
    
    main_api_keys = getattr(model_cfg, "api_keys", None)
    llm = await llm_manager.get_llm_from_config(model_cfg, api_keys=main_api_keys)
    
    # Use FileEventLogBackend to record trace
    backend = FileEventLogBackend(log_dir=_EVENT_LOG_DIR, session_id=message_id)
    
    agent = BaseAgent(
        llm=llm,
        event_log_backend=backend,
    )
    
    # Run agent
    async for _ in agent.run(query=query, message_id=message_id, context={"session_id": message_id}):
        pass
        
    # Build trace and verify ttft_ms is recorded
    trace = await build_trace(backend, message_id)
    
    # Verify trace has at least one LLM call
    assert len(trace.llm_calls) > 0, "No LLM calls found in trace"
    
    first_call = trace.llm_calls[0]
    # Verify ttft_ms extraction is positive
    assert first_call.ttft_ms is not None, "ttft_ms should not be None"
    assert first_call.ttft_ms > 0, "ttft_ms should be greater than 0"
    # Verify duration extraction is positive
    assert first_call.duration_ms is not None, "duration_ms should not be None"
    assert first_call.duration_ms > 0, "duration_ms should be greater than 0"
    assert first_call.total_tokens > 0, "total_tokens should be greater than 0"
