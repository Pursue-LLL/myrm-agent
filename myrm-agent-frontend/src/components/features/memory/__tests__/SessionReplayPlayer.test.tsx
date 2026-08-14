/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ExecutionTrace } from '@/services/statistics';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('@/services/chat', () => ({
  getMessages: vi.fn().mockResolvedValue({
    messages: [],
    has_more: false,
    next_cursor: null,
  }),
}));

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: unknown) => unknown) =>
    selector({ chatId: null, messages: [] }),
}));

vi.mock('@/components/features/memory/replay/ReplayMessageBubble', () => ({
  default: () => null,
}));

import SessionReplayPlayer from '@/components/features/memory/replay/SessionReplayPlayer';

function baseTrace(overrides?: Partial<ExecutionTrace>): ExecutionTrace {
  return {
    session_id: 'sess-1',
    metadata: { user_id: null, agent_id: null, task_type: null, trace_id: null },
    outcome: 'success',
    start_time: 1000,
    end_time: 1003,
    duration_ms: 3000,
    task_input: 'run pwd',
    output: 'done',
    tool_calls: [
      {
        sequence: 1,
        tool_name: 'bash',
        start_time: 1000,
        end_time: 1002,
        duration_ms: 2000,
        success: true,
        error: null,
        tool_call_id: 'call-1',
        message_id: 'm1',
      },
    ],
    llm_calls: [],
    errors: [],
    human_feedback: [],
    memory_events: [],
    total_events: 2,
    total_tokens: 0,
    ...overrides,
  };
}

describe('SessionReplayPlayer security labels', () => {
  it('renders the critical security flag chip when a tool call carries a DENY label', async () => {
    const trace = baseTrace({
      tool_calls: [
        {
          sequence: 1,
          tool_name: 'bash',
          start_time: 1000,
          end_time: 1002,
          duration_ms: 2000,
          success: true,
          error: null,
          tool_call_id: 'call-1',
          message_id: 'm1',
          security_labels: [
            { decision: 'DENY', reason: 'rm -rf blocked', tainted: true, ts: 1000.5 },
          ],
        },
      ],
    });
    const { container } = render(<SessionReplayPlayer sessionId="sess-1" trace={trace} />);

    expect(await screen.findByText('bash')).toBeInTheDocument();
    const flag = screen.getByText('securityFlag');
    // tainted + DENY must paint the chip with the critical (rose) palette.
    expect(flag.className).toContain('bg-rose-500/10');
    expect(flag.getAttribute('title')).toContain('rm -rf blocked');
  });

  it('paints the non-critical amber chip for a plain security label without deny/taint', async () => {
    const trace = baseTrace({
      tool_calls: [
        {
          sequence: 1,
          tool_name: 'bash',
          start_time: 1000,
          end_time: 1002,
          duration_ms: 2000,
          success: true,
          error: null,
          tool_call_id: 'call-1',
          message_id: 'm1',
          security_labels: [
            { decision: 'ALLOW', reason: 'low risk', tainted: false, ts: 1000.5 },
          ],
        },
      ],
    });
    const { container } = render(<SessionReplayPlayer sessionId="sess-1" trace={trace} />);

    const flag = await screen.findByText('securityFlag');
    expect(flag.className).toContain('bg-amber-500/10');
  });

  it('shows no security chip when the tool call has no security labels', async () => {
    render(<SessionReplayPlayer sessionId="sess-1" trace={baseTrace()} />);
    expect(await screen.findByText('bash')).toBeInTheDocument();
    expect(screen.queryByText('securityFlag')).not.toBeInTheDocument();
  });

  it('renders the decision detail (decision + reason) in the inspector', async () => {
    const trace = baseTrace({
      tool_calls: [
        {
          sequence: 1,
          tool_name: 'bash',
          start_time: 1000,
          end_time: 1002,
          duration_ms: 2000,
          success: true,
          error: null,
          tool_call_id: 'call-1',
          message_id: 'm1',
          security_labels: [
            { decision: 'DENY', reason: 'destructive path blocked', tainted: true, ts: 1000.5 },
          ],
        },
      ],
    });
    render(<SessionReplayPlayer sessionId="sess-1" trace={trace} />);

    expect(await screen.findByText('securityLabels')).toBeInTheDocument();
    expect(screen.getByText('DENY')).toBeInTheDocument();
    expect(screen.getByText('destructive path blocked')).toBeInTheDocument();
  });
});
