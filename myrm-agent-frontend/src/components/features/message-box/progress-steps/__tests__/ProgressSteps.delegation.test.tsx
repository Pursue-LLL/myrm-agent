/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: unknown) => unknown) => selector({ sendMessage: vi.fn(), messages: [] }),
}));

import ProgressSteps from '../ProgressSteps';
import type { ProgressItem } from '@/store/chat/types';

const LINE = 'claude: Read — note.txt';

const toolStep = (overrides: Partial<ProgressItem> = {}): ProgressItem => ({
  step_key: 'delegation_claude_tool',
  tool_name: 'delegate:claude',
  tool_call_id: 'toolu_1',
  items: [{ text: LINE }],
  status: 'complete',
  ...overrides,
});

const open = async (steps: ProgressItem[]) => {
  render(<ProgressSteps messageId="m-1" steps={steps} loading={false} />);
  await userEvent.click(screen.getByTestId('progress-steps-toggle'));
};

describe('ProgressSteps delegated external agent steps', () => {
  it('shows a delegated tool call once, as the step title', async () => {
    await open([toolStep()]);
    expect(screen.getAllByText(LINE)).toHaveLength(1);
  });

  it('keeps every tool call of the turn as its own line', async () => {
    await open([toolStep(), toolStep({ tool_call_id: 'toolu_2', items: [{ text: 'claude: Bash — ls' }] })]);
    expect(screen.getAllByText(LINE)).toHaveLength(1);
    expect(screen.getAllByText('claude: Bash — ls')).toHaveLength(1);
  });

  it('still shows the status text of the delegation status line in the body', async () => {
    await open([
      {
        step_key: 'delegation_claude_status',
        tool_name: 'delegate:claude',
        items: [{ text: 'claude: completed' }],
        status: 'complete',
      },
    ]);
    expect(screen.getByText('claude: completed')).toBeInTheDocument();
    expect(screen.getByText('delegation')).toBeInTheDocument();
  });

  it('renders a continuity notice as a title-only step', async () => {
    await open([
      { step_key: 'delegation_claude_session_expired', tool_name: 'delegate:claude', items: [], status: 'complete' },
    ]);
    expect(screen.getByText('delegation_session_expired')).toBeInTheDocument();
  });

  it('still shows the error of a failed delegated tool call', async () => {
    await open([toolStep({ status: 'error', error: 'Permission denied' })]);
    expect(screen.getAllByText(LINE)).toHaveLength(1);
    expect(screen.getByText('Permission denied')).toBeInTheDocument();
  });
});
