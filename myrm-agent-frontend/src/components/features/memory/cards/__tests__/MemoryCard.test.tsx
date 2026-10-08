import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import MemoryCard from '../MemoryCard';
import { TooltipProvider } from '@/components/primitives/tooltip';
import type { PendingMemory } from '@/services/memory/core';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

const fallbacks: Record<string, string> = {
  'fields.willCorrect': 'Corrects an existing memory',
  'fields.willDelete': 'Removes an existing memory',
  'fields.targetContent': 'Target',
  reject: 'Reject',
  accept: 'Accept',
};

const stableT = (key: string, options?: { defaultMessage?: string }) =>
  fallbacks[key] ?? options?.defaultMessage ?? key;

vi.mock('next-intl', () => ({ useTranslations: () => stableT }));

const basePending: PendingMemory = {
  id: 'pending-1',
  user_id: 'user-1',
  memory_type: 'semantic',
  content: 'User now works at Google',
  status: 'pending',
  created_at: '2026-08-15T12:00:00Z',
};

const renderCard = (overrides: Partial<PendingMemory>) =>
  render(
    <TooltipProvider>
      <MemoryCard memory={{ ...basePending, ...overrides }} variant="pending" />
    </TooltipProvider>,
  );

describe('MemoryCard pending target hint', () => {
  it('shows the correction hint with the target content for a CORRECT proposal', () => {
    renderCard({
      resolution_action: 'correct',
      target_memory_id: 'mem-old',
      target_content: 'User works at ByteDance',
    });

    const hint = screen.getByTestId('pending-target-hint');
    expect(hint).toHaveTextContent('Corrects an existing memory');
    expect(hint).toHaveTextContent('User works at ByteDance');
  });

  it('shows the removal hint for a DELETE proposal', () => {
    renderCard({
      resolution_action: 'delete',
      target_memory_id: 'mem-old',
      target_content: 'User lives in Berlin',
    });

    const hint = screen.getByTestId('pending-target-hint');
    expect(hint).toHaveTextContent('Removes an existing memory');
    expect(hint).toHaveTextContent('User lives in Berlin');
  });

  it('renders no target hint for a plain STORE proposal', () => {
    renderCard({ resolution_action: 'store' });

    expect(screen.queryByTestId('pending-target-hint')).not.toBeInTheDocument();
  });

  it('omits the target body when no target content is provided', () => {
    renderCard({ resolution_action: 'correct' });

    const hint = screen.getByTestId('pending-target-hint');
    expect(hint).toHaveTextContent('Corrects an existing memory');
    expect(hint).not.toHaveTextContent('Target');
  });
});
