/** @vitest-environment jsdom */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockListChannelStatuses = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, opts?: { fallback?: string }) => opts?.fallback ?? key,
}));

vi.mock('@/services/channels', () => ({
  listChannelStatuses: () => mockListChannelStatuses(),
}));

import { AgentNotifyTargets } from '../AgentNotifyTargets';
import type { NotifyTarget } from '@/services/agent';

describe('AgentNotifyTargets', () => {
  beforeEach(() => {
    mockListChannelStatuses.mockResolvedValue([{ name: 'telegram', status: 'running' }]);
  });

  it('shows empty hint when no channels connected', async () => {
    mockListChannelStatuses.mockResolvedValue([]);
    render(<AgentNotifyTargets targets={[]} onChange={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText(/Connect a channel/i)).toBeInTheDocument();
    });
  });

  it('adds a notify target when add button clicked', async () => {
    const onChange = vi.fn();
    render(<AgentNotifyTargets targets={[]} onChange={onChange} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Add Notification Target/i })).toBeEnabled();
    });

    fireEvent.click(screen.getByRole('button', { name: /Add Notification Target/i }));

    expect(onChange).toHaveBeenCalledWith([
      { channel: 'telegram', recipient_id: '', label: '' },
    ]);
  });

  it('updates recipient_id field', async () => {
    const targets: NotifyTarget[] = [{ channel: 'telegram', recipient_id: '', label: '' }];
    const onChange = vi.fn();
    render(<AgentNotifyTargets targets={targets} onChange={onChange} />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Recipient ID')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText('Recipient ID'), {
      target: { value: 'chat_123' },
    });

    expect(onChange).toHaveBeenCalledWith([
      { channel: 'telegram', recipient_id: 'chat_123', label: '' },
    ]);
  });

  it('removes target on trash click', async () => {
    const targets: NotifyTarget[] = [{ channel: 'telegram', recipient_id: 'chat_1', label: 'TG' }];
    const onChange = vi.fn();
    const { container } = render(<AgentNotifyTargets targets={targets} onChange={onChange} />);

    await waitFor(() => {
      expect(screen.getByDisplayValue('chat_1')).toBeInTheDocument();
    });

    const trashButton = container.querySelector('button.text-destructive, button .text-destructive')?.closest('button')
      ?? container.querySelector('button[class*="destructive"]');
    expect(trashButton).toBeTruthy();
    fireEvent.click(trashButton!);

    expect(onChange).toHaveBeenCalledWith([]);
  });
});
