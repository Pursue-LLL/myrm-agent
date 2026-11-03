/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const stableT = (key: string, values?: Record<string, unknown>) =>
  values ? `${key}:${Object.values(values).join('/')}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const fetchWithTimeoutMock = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({ fetchWithTimeout: fetchWithTimeoutMock }));

import { AgentToolDiagnostics } from '../AgentToolDiagnostics';

const respondWith = (data: unknown[]) =>
  fetchWithTimeoutMock.mockResolvedValue({ json: async () => ({ data }) } as unknown as Response);

beforeEach(() => {
  fetchWithTimeoutMock.mockReset();
});

describe('AgentToolDiagnostics localized copy', () => {
  it('labels the trigger, dialog title and every metric of a tool row', async () => {
    respondWith([
      {
        tool_name: 'web_search',
        total_calls: 12,
        success_count: 9,
        error_count: 3,
        avg_duration: 1.234,
        max_duration: 4,
      },
    ]);
    render(<AgentToolDiagnostics agentId="agent-1" />);

    await userEvent.click(screen.getByText('trigger'));

    expect(screen.getByText('title')).toBeInTheDocument();
    expect(await screen.findByText('web_search')).toBeInTheDocument();
    expect(screen.getByText('calls:12')).toBeInTheDocument();
    expect(screen.getByText('successRate')).toBeInTheDocument();
    expect(screen.getByText('errors')).toBeInTheDocument();
    expect(screen.getByText('avgTime')).toBeInTheDocument();
  });

  it('shows the loading text first and the empty state when the agent has no data', async () => {
    respondWith([]);
    render(<AgentToolDiagnostics agentId="agent-1" />);

    await userEvent.click(screen.getByText('trigger'));

    expect(await screen.findByText('empty')).toBeInTheDocument();
    expect(screen.queryByText('loading')).not.toBeInTheDocument();
  });
});
