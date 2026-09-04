/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('../cards/MemoryTypeIcon', () => ({
  default: () => null,
}));

import MemoryCard from '../cards/MemoryCard';
import type { Memory } from '@/store/memory';

const baseProcedural: Memory = {
  id: 'rule-1',
  memory_type: 'procedural',
  content: "Tool 'web_fetch_tool' failed 2 times in this session",
  trigger: 'web_fetch_tool repeated failure',
  action: 'Consider alternative approach when using web_fetch_tool.',
  expected_valid_days: 1,
  status: 'active',
  created_at: '2026-08-13T00:00:00Z',
  updated_at: '2026-08-13T00:00:00Z',
};

describe('MemoryCard - procedural TTL display', () => {
  it('shows the TTL line for an unlocked failure rule', () => {
    render(<MemoryCard memory={baseProcedural} variant="confirmed" />);
    expect(screen.getByText('fields.ttlDays')).toBeInTheDocument();
  });

  it('hides the TTL line for a user-locked rule (permanent retention)', () => {
    render(<MemoryCard memory={{ ...baseProcedural, is_user_locked: true }} variant="confirmed" />);
    expect(screen.queryByText('fields.ttlDays')).not.toBeInTheDocument();
  });
});

describe('MemoryCard - delete actions', () => {
  it('calls onDelete with false for regular soft delete', async () => {
    const onDeleteMock = vi.fn();
    render(
      <MemoryCard
        memory={baseProcedural}
        variant="confirmed"
        onDelete={onDeleteMock}
      />,
    );

    // Open actions menu
    const moreButton = screen.getByRole('button', { name: '' });
    moreButton.click();

    const deleteBtn = screen.getByText('delete');
    deleteBtn.click();

    expect(onDeleteMock).toHaveBeenCalledWith(false);
  });

  it('calls onDelete with true for permanent physical shredding', async () => {
    const onDeleteMock = vi.fn();
    render(
      <MemoryCard
        memory={baseProcedural}
        variant="confirmed"
        onDelete={onDeleteMock}
      />,
    );

    // Open actions menu
    const moreButton = screen.getByRole('button', { name: '' });
    moreButton.click();

    const permBtn = screen.getByText('trash.permanentDelete');
    permBtn.click();

    expect(onDeleteMock).toHaveBeenCalledWith(true);
  });
});
