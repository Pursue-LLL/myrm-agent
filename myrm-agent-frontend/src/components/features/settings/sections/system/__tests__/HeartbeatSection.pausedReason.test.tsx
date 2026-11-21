// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { jsonResponse } from '@/test-utils/riskHeld';

const { agentState } = vi.hoisted(() => ({
  agentState: { agents: [] as never[], fetchAgents: vi.fn() },
}));

vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: vi.fn(async () => true),
  markLocalBackendUnreachable: vi.fn(),
}));
vi.mock('@/store/useAgentStore', () => ({ default: () => agentState }));

import HeartbeatSection from '../HeartbeatSection';

const heartbeatStatus = (enabled: boolean, pausedReason: string | null) => ({
  enabled,
  interval_ms: 1_800_000,
  schedule_kind: 'interval',
  cron_expr: null,
  timezone: null,
  schedule_description: null,
  prompt: 'check in',
  model: null,
  agent_id: null,
  last_run_at: null,
  last_status: null,
  next_run_at: null,
  fire_count: 3,
  paused_reason: pausedReason,
});

describe('why the heartbeat is off, beside its switch', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const serve = (status: ReturnType<typeof heartbeatStatus>) =>
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(200, status)),
    );

  // The mocked translator echoes keys, so each sentence shows up as the key it is read from.
  it.each([
    ['circuit_break', 'circuitBreakBanner'],
    ['run_failures', 'pausedRunFailures'],
    ['schedule_error', 'pausedScheduleError'],
  ])('words a pause the scheduler gave for %s as %s', async (reason, sentence) => {
    serve(heartbeatStatus(false, reason));

    render(<HeartbeatSection />);

    expect(await screen.findByText(sentence)).toHaveClass('text-destructive-text');
  });

  it('says nothing about a heartbeat the user switched off', async () => {
    serve(heartbeatStatus(false, null));

    render(<HeartbeatSection />);

    await screen.findByText('toggleLabel');
    expect(screen.queryByText(/^(circuitBreakBanner|pausedRunFailures|pausedScheduleError)$/)).not.toBeInTheDocument();
  });

  it('says nothing about a heartbeat that is running', async () => {
    serve(heartbeatStatus(true, null));

    render(<HeartbeatSection />);

    await screen.findByText('toggleLabel');
    expect(screen.queryByText(/^(circuitBreakBanner|pausedRunFailures|pausedScheduleError)$/)).not.toBeInTheDocument();
  });
});
