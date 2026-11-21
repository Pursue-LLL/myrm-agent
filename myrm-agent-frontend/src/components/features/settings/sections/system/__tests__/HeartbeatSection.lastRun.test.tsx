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

const heartbeatStatus = (lastStatus: string) => ({
  enabled: true,
  interval_ms: 1_800_000,
  schedule_kind: 'interval',
  cron_expr: null,
  timezone: null,
  schedule_description: null,
  prompt: 'check in',
  model: null,
  agent_id: null,
  last_run_at: '2026-11-16T09:00:00Z',
  last_status: lastStatus,
  next_run_at: null,
  fire_count: 3,
});

describe('the last heartbeat run in the status line', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  // The mocked translator echoes keys, so each word shows up as the key it is read from.
  it.each([
    ['ok', 'runOk', 'text-green-600'],
    ['skipped', 'runSkipped', 'text-muted-foreground'],
    ['error', 'runError', 'text-destructive-text'],
    ['circuit_break', 'runCircuitBreak', 'text-destructive-text'],
  ])('words the status %s as %s and tints it %s', async (status, label, tone) => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(200, heartbeatStatus(status))),
    );
    render(<HeartbeatSection />);

    expect(await screen.findByText(`(${label})`)).toHaveClass(tone);
    expect(screen.queryByText(`(${status})`)).not.toBeInTheDocument();
  });
});
