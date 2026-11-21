/** @vitest-environment jsdom */
import { useState, type ReactNode } from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { expectNonNull } from '@/test-utils/expectDefined';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockListChannelStatuses = vi.fn();
const mockListPairings = vi.fn();

const stableT = (key: string, opts?: { fallback?: string }) => opts?.fallback ?? key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/channels', () => ({
  listChannelStatuses: () => mockListChannelStatuses(),
  listPairings: () => mockListPairings(),
}));

// Radix Select cannot be driven in jsdom; each item reports to the Select that contains it.
vi.mock('@/components/primitives/select', async () => {
  const { createContext, useContext } = await import('react');
  const PickContext = createContext<((value: string) => void) | undefined>(undefined);
  return {
    Select: ({ onValueChange, children }: { onValueChange?: (value: string) => void; children: ReactNode }) => (
      <PickContext.Provider value={onValueChange}>{children}</PickContext.Provider>
    ),
    SelectTrigger: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    SelectValue: ({ placeholder }: { placeholder?: string }) => <span>{placeholder}</span>,
    SelectContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    SelectItem: function SelectItem({ value, children }: { value: string; children: ReactNode }) {
      const pick = useContext(PickContext);
      return (
        <button type="button" onClick={() => pick?.(value)}>
          {children}
        </button>
      );
    },
  };
});

import { AgentNotifyTargets } from '../AgentNotifyTargets';
import type { NotifyTarget } from '@/services/agent';

function pairing(overrides: {
  id: string;
  channel: string;
  sender_id: string;
  role: 'admin' | 'member';
  display_name: string;
}) {
  return {
    user_id: 'sandbox',
    status: 'active',
    daily_quota: null,
    created_at: '2026-01-01',
    updated_at: '2026-01-01',
    ...overrides,
  };
}

/** The settings page owns the targets; the component only reports edits, so typing needs a parent that keeps them. */
function Editor({ initial, onEdit }: { initial: NotifyTarget[]; onEdit?: (targets: NotifyTarget[]) => void }) {
  const [targets, setTargets] = useState(initial);
  return (
    <AgentNotifyTargets
      targets={targets}
      onChange={(next) => {
        setTargets(next);
        onEdit?.(next);
      }}
    />
  );
}

describe('AgentNotifyTargets', () => {
  beforeEach(() => {
    mockListChannelStatuses.mockResolvedValue([{ name: 'telegram', status: 'running', displayName: 'Telegram' }]);
    mockListPairings.mockResolvedValue([]);
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

    expect(onChange).toHaveBeenCalledWith([{ channel: 'telegram', recipient_id: '', label: '' }]);
  });

  it('prefills the owner contact (admin pairing), not the first one listed, when adding a row', async () => {
    mockListPairings.mockResolvedValue([
      pairing({ id: 'p0', channel: 'telegram', sender_id: 'colleague_777', role: 'member', display_name: 'Colleague' }),
      pairing({ id: 'p1', channel: 'telegram', sender_id: 'chat_999', role: 'admin', display_name: 'My TG' }),
    ]);
    const onChange = vi.fn();
    render(<AgentNotifyTargets targets={[]} onChange={onChange} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Add Notification Target/i })).toBeEnabled();
    });

    fireEvent.click(screen.getByRole('button', { name: /Add Notification Target/i }));

    expect(onChange).toHaveBeenCalledWith([{ channel: 'telegram', recipient_id: 'chat_999', label: 'My TG' }]);
  });

  it('leaves the recipient to the user when the channel has contacts but none is the owner', async () => {
    mockListPairings.mockResolvedValue([
      pairing({ id: 'p0', channel: 'telegram', sender_id: 'colleague_777', role: 'member', display_name: 'Colleague' }),
    ]);
    const onEdit = vi.fn();
    render(<Editor initial={[]} onEdit={onEdit} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Add Notification Target/i })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole('button', { name: /Add Notification Target/i }));

    expect(onEdit).toHaveBeenCalledWith([{ channel: 'telegram', recipient_id: '', label: '' }]);
    expect(screen.getByText('Select recipient')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Recipient ID')).not.toBeInTheDocument();
  });

  it('prefills the owner contact of the new channel when a row switches channel', async () => {
    mockListChannelStatuses.mockResolvedValue([
      { name: 'telegram', status: 'running', displayName: 'Telegram' },
      { name: 'wechat', status: 'running', displayName: 'WeChat' },
    ]);
    mockListPairings.mockResolvedValue([
      pairing({ id: 'p1', channel: 'telegram', sender_id: 'chat_999', role: 'admin', display_name: 'My TG' }),
      pairing({ id: 'p2', channel: 'wechat', sender_id: 'wx_colleague', role: 'member', display_name: 'Colleague' }),
    ]);
    const onEdit = vi.fn();
    render(
      <Editor initial={[{ channel: 'wechat', recipient_id: 'wx_colleague', label: 'Colleague' }]} onEdit={onEdit} />,
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Telegram' }));
    expect(onEdit).toHaveBeenLastCalledWith([{ channel: 'telegram', recipient_id: 'chat_999', label: 'My TG' }]);

    fireEvent.click(screen.getByRole('button', { name: 'WeChat' }));
    expect(onEdit).toHaveBeenLastCalledWith([{ channel: 'wechat', recipient_id: '', label: '' }]);
  });

  it('shows manual input when saved recipient is not in pairings', async () => {
    mockListPairings.mockResolvedValue([
      pairing({ id: 'p1', channel: 'telegram', sender_id: 'chat_other', role: 'admin', display_name: 'Other' }),
    ]);
    const targets: NotifyTarget[] = [{ channel: 'telegram', recipient_id: 'legacy_manual_id', label: 'Legacy' }];
    render(<AgentNotifyTargets targets={targets} onChange={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByDisplayValue('legacy_manual_id')).toBeInTheDocument();
    });
    expect(screen.queryByText('notifySelectRecipient')).not.toBeInTheDocument();
  });

  it('updates recipient_id field in manual mode', async () => {
    const targets: NotifyTarget[] = [{ channel: 'telegram', recipient_id: '', label: '' }];
    const onChange = vi.fn();
    render(<AgentNotifyTargets targets={targets} onChange={onChange} />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Recipient ID')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText('Recipient ID'), {
      target: { value: 'chat_123' },
    });

    expect(onChange).toHaveBeenCalledWith([{ channel: 'telegram', recipient_id: 'chat_123', label: '' }]);
  });

  it('keeps every typed character of a manually entered recipient ID', async () => {
    const onEdit = vi.fn();
    render(<Editor initial={[{ channel: 'telegram', recipient_id: '', label: '' }]} onEdit={onEdit} />);

    const input = await screen.findByPlaceholderText('Recipient ID');
    await userEvent.setup().type(input, 'abc123');

    expect(screen.getByPlaceholderText('Recipient ID')).toHaveValue('abc123');
    expect(onEdit).toHaveBeenLastCalledWith([{ channel: 'telegram', recipient_id: 'abc123', label: '' }]);
  });

  it('keeps every typed character of a label', async () => {
    const onEdit = vi.fn();
    render(<Editor initial={[{ channel: 'telegram', recipient_id: 'chat_1', label: '' }]} onEdit={onEdit} />);

    const input = await screen.findByPlaceholderText('Label');
    await userEvent.setup().type(input, 'Team');

    expect(screen.getByPlaceholderText('Label')).toHaveValue('Team');
  });

  it('adds wechat target when only non-hardcoded channel is running', async () => {
    mockListChannelStatuses.mockResolvedValue([{ name: 'wechat', status: 'running', displayName: 'WeChat' }]);
    const onChange = vi.fn();
    render(<AgentNotifyTargets targets={[]} onChange={onChange} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Add Notification Target/i })).toBeEnabled();
    });

    fireEvent.click(screen.getByRole('button', { name: /Add Notification Target/i }));

    expect(onChange).toHaveBeenCalledWith([{ channel: 'wechat', recipient_id: '', label: '' }]);
  });

  it('removes target on trash click', async () => {
    const targets: NotifyTarget[] = [{ channel: 'telegram', recipient_id: 'chat_1', label: 'TG' }];
    const onChange = vi.fn();
    const { container } = render(<AgentNotifyTargets targets={targets} onChange={onChange} />);

    await waitFor(() => {
      expect(screen.getByDisplayValue('chat_1')).toBeInTheDocument();
    });

    const trashButton =
      container.querySelector('button.text-destructive-text, button .text-destructive-text')?.closest('button') ??
      container.querySelector('button[class*="destructive"]');
    expect(trashButton).toBeTruthy();
    expectNonNull(trashButton, 'trashButton');
    fireEvent.click(trashButton);

    expect(onChange).toHaveBeenCalledWith([]);
  });
});
