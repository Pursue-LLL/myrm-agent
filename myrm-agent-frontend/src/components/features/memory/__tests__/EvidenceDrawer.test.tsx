/** @vitest-environment jsdom */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EvidenceDrawer } from '../drawers/EvidenceDrawer';
import { EvidenceBadge } from '../cards/EvidenceBadge';
import * as commandCenterService from '@/services/memory/commandCenter';

const stableT = (key: string, values?: Record<string, string | number>) => {
  if (values) {
    return Object.entries(values).reduce(
      (acc, [k, v]) => acc.replace(`{${k}}`, String(v)),
      key
    );
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
      <EvidenceBadge
        sourceId="chat-alpha"
        messageId="msg-target"
        quoteSnippet="Standardize on pnpm"
        t={stableT}
      />
    );

    const badge = screen.getByRole('button');
    expect(badge).toBeInTheDocument();

    await userEvent.click(badge);

    expect(screen.getByText('commandCenter.evidence.drawerTitle')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Please standardize on pnpm across monorepo.')).toBeInTheDocument();
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
      />
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
});
