/** @vitest-environment jsdom */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EvidenceDrawer } from '../drawers/EvidenceDrawer';
import { EvidenceBadge } from '../cards/EvidenceBadge';
import * as commandCenterService from '@/services/memory/commandCenter';

const stableT = (key: string, values?: Record<string, string | number>) => {
  if (values) {
    return Object.entries(values).reduce((acc, [k, v]) => acc.replace(`{${k}}`, String(v)), key);
  }
  return key;
};

describe('EvidenceBadge and EvidenceDrawer Component', () => {
  const mockPlayback: commandCenterService.MemoryEvidencePlaybackResponse = {
    status: 'live_context',
    source_type: 'chat',
    source_id: 'chat-alpha',
    target_message_id: 'msg-target',
    quote_snippet: 'Standardize on pnpm',
    author_name: 'LeadArch',
    occurred_at: '2026-09-04T12:00:00Z',
    turns: [
      {
        message_id: 'msg-1',
        role: 'user',
        sender_name: 'LeadArch',
        content: 'Please standardize on pnpm across monorepo.',
        sent_at: '2026-09-04T12:00:00Z',
        is_target: true,
        is_self: true,
      },
    ],
    is_user_locked: false,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders EvidenceBadge when evidence attributes exist and opens drawer upon click', async () => {
    vi.spyOn(commandCenterService, 'getEvidencePlayback').mockResolvedValue(mockPlayback);

    render(
      <EvidenceBadge sourceId="chat-alpha" messageId="msg-target" quoteSnippet="Standardize on pnpm" t={stableT} />,
    );

    const badge = screen.getByRole('button');
    expect(badge).toBeInTheDocument();

    await userEvent.click(badge);

    expect(screen.getByText('commandCenter.evidence.drawerTitle')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/standardize on pnpm/i)).toBeInTheDocument();
    });
  });

  it('handles in-place fact correction in EvidenceDrawer', async () => {
    vi.spyOn(commandCenterService, 'getEvidencePlayback').mockResolvedValue(mockPlayback);
    const mockCorrectAndLock = vi.fn().mockResolvedValue(undefined);

    render(
      <EvidenceDrawer
        isOpen={true}
        onClose={vi.fn()}
        sourceId="chat-alpha"
        messageId="msg-target"
        quoteSnippet="Standardize on pnpm"
        onCorrectAndLock={mockCorrectAndLock}
        t={stableT}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('commandCenter.evidence.correctAndLock')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText('commandCenter.evidence.correctAndLock'));
    expect(screen.getByText('commandCenter.evidence.correctPrompt')).toBeInTheDocument();

    const saveBtn = screen.getByText('commandCenter.evidence.saveAndLock');
    await userEvent.click(saveBtn);

    expect(mockCorrectAndLock).toHaveBeenCalledWith('Standardize on pnpm');
  });

  it('renders tool execution verbatim error segment with terminal badge', async () => {
    const mockToolPlayback: commandCenterService.MemoryEvidencePlaybackResponse = {
      ...mockPlayback,
      turns: [
        {
          message_id: 'tool-msg-1',
          role: 'tool',
          sender_name: 'bash',
          content: 'Tool[bash] exit=1:\npytest tests/failed.py\nFAILED (failures=1)',
          sent_at: '2026-09-04T12:05:00Z',
          is_target: false,
        },
      ],
    };
    vi.spyOn(commandCenterService, 'getEvidencePlayback').mockResolvedValue(mockToolPlayback);

    render(<EvidenceDrawer isOpen={true} onClose={vi.fn()} sourceId="chat-alpha" t={stableT} />);

    await waitFor(() => {
      expect(screen.getByText('bash')).toBeInTheDocument();
      expect(screen.getByText('commandCenter.evidence.toolFailed')).toBeInTheDocument();
      expect(screen.getByText(/pytest tests\/failed\.py/)).toBeInTheDocument();
    });
  });

  it.each([
    ['Tool[bash] cmd=pytest exit=0\n0 errors, 0 failed', false],
    ['Tool[bash] cmd=make exit=137\nKilled', true],
    ['Tool[bash]\nTraceback: connection error', true],
  ])('classifies tool output %j as failure=%s', async (content, expectedFailure) => {
    vi.spyOn(commandCenterService, 'getEvidencePlayback').mockResolvedValue({
      ...mockPlayback,
      turns: [
        {
          message_id: 'tool-msg-2',
          role: 'tool',
          sender_name: 'bash',
          content,
          sent_at: '2026-09-04T12:05:00Z',
          is_target: false,
        },
      ],
    });

    render(<EvidenceDrawer isOpen={true} onClose={vi.fn()} sourceId="chat-alpha" t={stableT} />);

    await screen.findByText('bash');
    const badge = screen.queryByText('commandCenter.evidence.toolFailed');
    expect(badge !== null).toBe(expectedFailure);
  });

  it('shows the translated quote-match line when the quote is not found verbatim', async () => {
    vi.spyOn(commandCenterService, 'getEvidencePlayback').mockResolvedValue({
      ...mockPlayback,
      quote_snippet: 'Use pnpm!!',
    });

    render(<EvidenceDrawer isOpen={true} onClose={vi.fn()} sourceId="chat-alpha" t={stableT} />);

    await waitFor(() => {
      expect(screen.getByText('commandCenter.evidence.quoteMatch')).toBeInTheDocument();
    });
  });

  it('shows a localized message instead of the raw exception when loading fails', async () => {
    vi.spyOn(commandCenterService, 'getEvidencePlayback').mockRejectedValue(new Error('ECONNRESET 10.0.0.5'));

    render(<EvidenceDrawer isOpen={true} onClose={vi.fn()} sourceId="chat-alpha" t={stableT} />);

    await waitFor(() => {
      expect(screen.getByText('commandCenter.evidence.loadFailed')).toBeInTheDocument();
    });
    expect(screen.queryByText(/ECONNRESET/)).not.toBeInTheDocument();
  });
});
