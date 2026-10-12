import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import MemoryCard from '../MemoryCard';
import { TooltipProvider } from '@/components/primitives/tooltip';
import type { Memory, PendingMemory } from '@/services/memory/core';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

const fallbacks: Record<string, string> = {
  'fields.willCorrect': 'Corrects an existing memory',
  'fields.willDelete': 'Removes an existing memory',
  'fields.targetContent': 'Target',
  reject: 'Reject',
  accept: 'Accept',
  locked: 'Protected from auto-modification',
  exactFact: 'Exact fact',
  exactFactHint: 'Kept verbatim',
  usedTimes: 'Used {count} times',
  lastUsedAt: 'Last used: {time}',
  'fields.reasoning': 'Why',
  'fields.application': 'How',
  'fields.trigger': 'Trigger',
};

const stableT = (key: string, options?: Record<string, string | number>) => {
  const template = fallbacks[key] ?? (options?.defaultMessage as string | undefined) ?? key;
  return template.replace(/\{(\w+)\}/g, (_, name: string) => String(options?.[name] ?? ''));
};

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

describe('MemoryCard protection mark', () => {
  const baseMemory: Memory = {
    id: 'mem-1',
    memory_type: 'semantic',
    content: 'User prefers concise answers',
    status: 'active',
    created_at: '2026-08-15T12:00:00Z',
    updated_at: '2026-08-15T12:00:00Z',
  };

  const renderConfirmed = (overrides: Partial<Memory>) =>
    render(
      <TooltipProvider>
        <MemoryCard memory={{ ...baseMemory, ...overrides }} variant="confirmed" />
      </TooltipProvider>,
    );

  it('marks a protected memory once, with the localized label', () => {
    renderConfirmed({ is_user_locked: true });

    expect(screen.getAllByLabelText('Protected from auto-modification')).toHaveLength(1);
    expect(screen.getByTitle('Protected from auto-modification')).toBeInTheDocument();
  });

  it('shows no protection mark for an unprotected memory', () => {
    renderConfirmed({ is_user_locked: false });

    expect(screen.queryByLabelText('Protected from auto-modification')).not.toBeInTheDocument();
  });

  it('labels an exact fact through translations and lists its identifiers in the hint', () => {
    renderConfirmed({ is_exact_fact: true, exact_identifiers: ['10.0.3.21:8443', 'v2.4.1'] });

    expect(screen.getByText('Exact fact')).toBeInTheDocument();
    expect(screen.getByTitle('Kept verbatim: 10.0.3.21:8443, v2.4.1')).toBeInTheDocument();
  });

  it('falls back to the plain hint when an exact fact has no identifiers', () => {
    renderConfirmed({ is_exact_fact: true, exact_identifiers: [] });

    expect(screen.getByTitle('Kept verbatim')).toBeInTheDocument();
  });

  it('shows no exact-fact badge for an ordinary memory', () => {
    renderConfirmed({ is_exact_fact: false });

    expect(screen.queryByText('Exact fact')).not.toBeInTheDocument();
  });
});

describe('MemoryCard pending confidence badge', () => {
  it.each([
    [0.92, '92%', 'text-emerald-600'],
    [0.7, '70%', 'text-amber-600'],
    [0.3, '30%', 'text-muted-foreground'],
  ])('renders confidence %s in the matching tier', (confidence, label, toneClass) => {
    renderCard({ confidence });

    expect(screen.getByText(label).parentElement).toHaveClass(toneClass);
  });

  it('renders no confidence badge when confidence is absent', () => {
    renderCard({});

    expect(screen.queryByText(/%$/)).not.toBeInTheDocument();
  });
});

describe('MemoryCard usage stats and procedural details', () => {
  const confirmedMemory: Memory = {
    id: 'mem-2',
    memory_type: 'procedural',
    content: 'Run lint before commit',
    status: 'active',
    created_at: '2026-08-15T12:00:00Z',
    updated_at: '2026-08-15T12:00:00Z',
    access_count: 7,
    last_accessed_at: '2026-08-16T08:30:00Z',
    trigger: 'before commit',
    reasoning: 'keeps CI green',
    application: 'run bun run lint',
  };

  const renderConfirmed = (overrides: Partial<Memory> = {}) =>
    render(
      <TooltipProvider>
        <MemoryCard memory={{ ...confirmedMemory, ...overrides }} variant="confirmed" />
      </TooltipProvider>,
    );

  it('interpolates the usage count and last-used time through translations', () => {
    renderConfirmed();

    expect(screen.getByText('Used 7 times')).toBeInTheDocument();
    expect(screen.getByText(/^Last used: .+/)).toBeInTheDocument();
  });

  it('omits the last-used line when the memory was never retrieved', () => {
    renderConfirmed({ access_count: 0, last_accessed_at: undefined });

    expect(screen.getByText('Used 0 times')).toBeInTheDocument();
    expect(screen.queryByText(/^Last used:/)).not.toBeInTheDocument();
  });

  it('labels procedural reasoning and application through translations', () => {
    renderConfirmed();

    expect(screen.getByText('Why:')).toBeInTheDocument();
    expect(screen.getByText('How:')).toBeInTheDocument();
  });
});
