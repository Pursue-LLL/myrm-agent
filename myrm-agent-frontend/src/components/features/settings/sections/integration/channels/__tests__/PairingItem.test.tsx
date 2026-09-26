/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import type { ChannelPairing } from '@/services/channels/manage';

const stableT = (key: string, values?: Record<string, unknown>) => {
  if (values && 'quota' in values) {
    return `${key}:${values.quota}`;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconCheck: () => <span data-testid="icon-check" />,
  IconX: () => <span data-testid="icon-x" />,
  IconTrash: () => <span data-testid="icon-trash" />,
  IconShield: () => <span data-testid="icon-shield" />,
  IconRefresh: () => <span data-testid="icon-refresh" />,
  IconUser: () => <span data-testid="icon-user" />,
  IconEdit: () => <span data-testid="icon-edit" />,
  IconPencil: () => <span data-testid="icon-pencil" />,
  IconCheckCircle: () => <span data-testid="icon-check-circle" />,
  IconBan: () => <span data-testid="icon-ban" />,
  IconLock: () => <span data-testid="icon-lock" />,
  IconLoader: () => <span data-testid="icon-loader" />,
}));

import { PairingItem } from '../PairingItem';

describe('PairingItem', () => {
  const mockPairing: ChannelPairing = {
    id: 'pair_123',
    channel: 'telegram',
    sender_id: 'user_456',
    status: 'active',
    role: 'member',
    daily_quota: 25,
    user_id: 'paired_member_telegram_user_456',
    display_name: 'Alice',
    created_at: '2026-03-26T12:00:00Z',
    updated_at: '2026-03-26T12:00:00Z',
  };

  const mockOnUpdateStatus = vi.fn();
  const mockOnDelete = vi.fn();
  const mockOnUpdateDisplayName = vi.fn();
  const mockOnUpdateRole = vi.fn();
  const mockOnUpdateQuota = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders pairing details with role badge and quota display', () => {
    render(
      <PairingItem
        pairing={mockPairing}
        isUpdating={false}
        channelLabel={(c) => c}
        onUpdateStatus={mockOnUpdateStatus}
        onDeleteRequest={mockOnDelete}
        onUpdateDisplayName={mockOnUpdateDisplayName}
        onUpdateRole={mockOnUpdateRole}
        onUpdateDailyQuota={mockOnUpdateQuota}
        t={stableT}
      />
    );

    expect(screen.getByText('Alice')).toBeTruthy();
    expect(screen.getByText('roleMemberBadge')).toBeTruthy();
    expect(screen.getByText('dailyQuotaDisplay:25')).toBeTruthy();
  });

  it('switches role from member to admin when clicking role badge', () => {
    render(
      <PairingItem
        pairing={mockPairing}
        isUpdating={false}
        channelLabel={(c) => c}
        onUpdateStatus={mockOnUpdateStatus}
        onDeleteRequest={mockOnDelete}
        onUpdateDisplayName={mockOnUpdateDisplayName}
        onUpdateRole={mockOnUpdateRole}
        onUpdateDailyQuota={mockOnUpdateQuota}
        t={stableT}
      />
    );

    const roleBadge = screen.getByText('roleMemberBadge');
    fireEvent.click(roleBadge);

    expect(mockOnUpdateRole).toHaveBeenCalledWith('pair_123', 'admin');
  });

  it('allows inline editing of daily quota', () => {
    render(
      <PairingItem
        pairing={mockPairing}
        isUpdating={false}
        channelLabel={(c) => c}
        onUpdateStatus={mockOnUpdateStatus}
        onDeleteRequest={mockOnDelete}
        onUpdateDisplayName={mockOnUpdateDisplayName}
        onUpdateRole={mockOnUpdateRole}
        onUpdateDailyQuota={mockOnUpdateQuota}
        t={stableT}
      />
    );

    // Click edit quota button
    const editBtn = screen.getByTitle('editQuota');
    act(() => {
      fireEvent.click(editBtn);
    });

    // Input new quota
    const input = screen.getByPlaceholderText('unlimitedQuota');
    act(() => {
      fireEvent.change(input, { target: { value: '100' } });
    });

    // Click save (IconCheck button)
    const saveBtn = screen.getByTestId('icon-check').parentElement;
    expect(saveBtn).toBeTruthy();
    if (saveBtn) {
      act(() => {
        fireEvent.click(saveBtn);
      });
    }

    expect(mockOnUpdateQuota).toHaveBeenCalledWith('pair_123', 100);
  });
});
