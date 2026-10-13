/**
 * Transport choice of an agent-stream turn: the request body (`multiplexed`) and the consumer share this one answer,
 * so a change here moves every chat between the workspace multiplex stream and the POST response body.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { shouldUseMultiplexedAgentStream } from '../streamConsumer';

describe('shouldUseMultiplexedAgentStream', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    delete window.__MYRM_E2E_DIRECT_SSE__;
  });

  it('multiplexes by default', () => {
    expect(shouldUseMultiplexedAgentStream()).toBe(true);
  });

  it('opts out only through the direct-SSE flag', () => {
    window.__MYRM_E2E_DIRECT_SSE__ = true;
    expect(shouldUseMultiplexedAgentStream()).toBe(false);

    window.__MYRM_E2E_DIRECT_SSE__ = false;
    expect(shouldUseMultiplexedAgentStream()).toBe(true);
  });

  it('multiplexes where there is no window', () => {
    vi.stubGlobal('window', undefined);
    expect(shouldUseMultiplexedAgentStream()).toBe(true);
  });
});
