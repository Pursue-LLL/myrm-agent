// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { installEnglishToastTranslator, jsonResponse, riskHeldRefusalBody, riskHeldTitle } from '@/test-utils/riskHeld';

const { sonnerToast, riskToast, agentState } = vi.hoisted(() => ({
  sonnerToast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
  riskToast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
  agentState: { agents: [] as never[], fetchAgents: vi.fn() },
}));

vi.mock('sonner', () => ({ toast: sonnerToast }));
vi.mock('@/lib/utils/toast', () => ({ toast: riskToast }));
vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: vi.fn(async () => true),
  markLocalBackendUnreachable: vi.fn(),
}));
vi.mock('@/store/useAgentStore', () => ({ default: () => agentState }));

import HeartbeatSection from '../HeartbeatSection';

const HELD_PROMPT = 'check the deploy with key sk-AAAAAABBBBBBCCCCCCDDDD-0';

const heartbeatStatus = (enabled: boolean) => ({
  enabled,
  interval_ms: 1_800_000,
  schedule_kind: 'interval',
  cron_expr: null,
  timezone: null,
  schedule_description: null,
  prompt: HELD_PROMPT,
  model: null,
  agent_id: null,
  last_run_at: null,
  last_status: null,
  next_run_at: null,
  fire_count: 0,
});

/** The status request is answered normally; the enable request gets `enableReply`. */
function stubHeartbeatApi(enabled: boolean, enableReply: () => Response): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: RequestInfo | URL) =>
      String(url).includes('/heartbeat/status') ? jsonResponse(200, heartbeatStatus(enabled)) : enableReply(),
    ),
  );
}

describe('turning on or saving a heartbeat whose prompt the server holds', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installEnglishToastTranslator();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('explains a held prompt once when saving and keeps the prompt in the box', async () => {
    stubHeartbeatApi(true, () => jsonResponse(400, riskHeldRefusalBody));
    render(<HeartbeatSection />);

    fireEvent.click(await screen.findByRole('button', { name: 'saveConfig' }));

    await waitFor(() => expect(riskToast.error).toHaveBeenCalledTimes(1));
    expect(riskToast.error.mock.calls[0]?.[0]).toBe(riskHeldTitle);
    expect(sonnerToast.error).not.toHaveBeenCalled();
    expect(screen.getByDisplayValue(HELD_PROMPT)).toBeDefined();
  });

  it('explains a held prompt once when turning the heartbeat on', async () => {
    stubHeartbeatApi(false, () => jsonResponse(400, riskHeldRefusalBody));
    render(<HeartbeatSection />);

    fireEvent.click(await screen.findByRole('switch'));

    await waitFor(() => expect(riskToast.error).toHaveBeenCalledTimes(1));
    expect(riskToast.error.mock.calls[0]?.[0]).toBe(riskHeldTitle);
    expect(sonnerToast.error).not.toHaveBeenCalled();
  });

  it('still reports any other failure with its own toast', async () => {
    stubHeartbeatApi(true, () => jsonResponse(500, { detail: 'boom' }));
    render(<HeartbeatSection />);

    fireEvent.click(await screen.findByRole('button', { name: 'saveConfig' }));

    await waitFor(() => expect(sonnerToast.error).toHaveBeenCalledWith('saveError'));
  });
});
