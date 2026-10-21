import { describe, expect, it } from 'vitest';

import { isStatusProgressStep } from '../statusStreamProgressSteps';

describe('statusStreamProgressSteps allowed_tools recovery', () => {
  it('recognizes allowed_tools_rejected_recovery as a progress step', () => {
    expect(isStatusProgressStep('allowed_tools_rejected_recovery')).toBe(true);
  });

  it('recognizes stream recovery progress steps', () => {
    expect(isStatusProgressStep('thinking_signature_recovery')).toBe(true);
    expect(isStatusProgressStep('tool_history_recovery')).toBe(true);
    expect(isStatusProgressStep('image_shrink_recovery')).toBe(true);
    expect(isStatusProgressStep('image_payload_recovery')).toBe(true);
    expect(isStatusProgressStep('long_context_tier_recovery')).toBe(true);
    expect(isStatusProgressStep('media_rejected_recovery')).toBe(true);
  });

  it('recognizes turn prewarm progress steps', () => {
    expect(isStatusProgressStep('turn_prewarm_agent')).toBe(true);
    expect(isStatusProgressStep('turn_prewarm_memory')).toBe(true);
    expect(isStatusProgressStep('turn_prewarm_agent_clear')).toBe(true);
    expect(isStatusProgressStep('turn_prewarm_memory_clear')).toBe(true);
    expect(isStatusProgressStep('wiki_knowledge_lane')).toBe(true);
    expect(isStatusProgressStep('wiki_knowledge_lane_clear')).toBe(true);
  });
});
