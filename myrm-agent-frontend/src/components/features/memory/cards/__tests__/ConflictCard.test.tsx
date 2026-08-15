import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ConflictCard from '../ConflictCard';
import type { PendingMemory } from '@/services/memory/core';

const mockResolve = vi.fn();

const FIXED_NOW = new Date('2026-08-15T12:00:00Z');

const conflictFallbacks: Record<string, string> = {
  'conflict.title': 'Memory Conflict',
  'conflict.importance': 'Importance',
  'conflict.highRisk': 'High risk',
  'conflict.currentMemory': 'Current Memory',
  'conflict.unknown': '(Content unavailable)',
  'conflict.newMemory': 'New Extracted Content',
  'conflict.mergedContent': 'Merged Content',
  'conflict.mergePlaceholder': 'Edit the merged memory content...',
  'conflict.accuracy': 'Accuracy',
  'conflict.keepOld': 'Keep Old',
  'conflict.keepNew': 'Use New',
  'conflict.merge': 'Merge',
  'conflict.confirmMerge': 'Confirm Merge',
  'conflict.discardBoth': 'Discard Both',
  'conflict.autoResolveNever': "Won't auto-resolve — needs manual review",
  'conflict.autoResolveSoon': 'Auto-resolving soon',
  'conflict.autoResolveInHours': 'Auto-resolves in {hours} hours (keeps old)',
  'conflict.autoResolveInMinutes': 'Auto-resolves in {minutes} min (keeps old)',
  'conflict.autoResolveInDays': 'Auto-resolves in {days} days (keeps old)',
};

const stableTranslate = (key: string, options?: { defaultMessage?: string; [k: string]: unknown }) => {
  if (options?.days !== undefined) {
    return `Auto-resolves in ${options.days} days (keeps old)`;
  }
  if (options?.hours !== undefined) {
    return `Auto-resolves in ${options.hours} hours (keeps old)`;
  }
  if (options?.minutes !== undefined) {
    return `Auto-resolves in ${options.minutes} min (keeps old)`;
  }
  return conflictFallbacks[key] ?? options?.defaultMessage ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableTranslate,
}));

const baseConflict: PendingMemory = {
  id: 'conflict-1',
  user_id: 'user-1',
  memory_type: 'semantic',
  content: 'New preference: use Go and PostgreSQL',
  status: 'pending',
  created_at: '2024-01-01T00:00:00Z',
  is_conflict: true,
  conflict_old_memory_id: 'old-1',
  conflict_old_content: 'Old preference: use Python and SQLite',
  conflict_accuracy_score: 0.7,
  conflict_importance: 0.8,
};

describe('ConflictCard', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(FIXED_NOW);
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders auto-resolve countdown for low-risk conflicts', () => {
    const inThreeDays = new Date(FIXED_NOW.getTime() + 3 * 24 * 60 * 60 * 1000).toISOString();
    render(
      <ConflictCard
        conflict={{ ...baseConflict, conflict_importance: 0.8, conflict_auto_resolve_at: inThreeDays }}
        onResolve={mockResolve}
      />,
    );

    expect(screen.getByText(/Auto-resolves in 3 days/)).toBeInTheDocument();
    expect(screen.queryByText(/Won't auto-resolve/)).not.toBeInTheDocument();
  });

  it('shows manual-review notice for high-risk conflicts (no auto_resolve_at)', () => {
    render(
      <ConflictCard
        conflict={{ ...baseConflict, conflict_importance: 0.95, conflict_auto_resolve_at: undefined }}
        onResolve={mockResolve}
      />,
    );

    expect(screen.getByText(/Won't auto-resolve/)).toBeInTheDocument();
    expect(screen.queryByText(/Auto-resolves in/)).not.toBeInTheDocument();
  });

  it('renders high-risk badge for importance >= 90%', () => {
    render(
      <ConflictCard
        conflict={{ ...baseConflict, conflict_importance: 0.95, conflict_auto_resolve_at: undefined }}
        onResolve={mockResolve}
      />,
    );

    expect(screen.getByText(/High risk/)).toBeInTheDocument();
  });

  it('shows high-risk badge for any high-risk conflict with importance (no 90% gate)', () => {
    render(
      <ConflictCard
        conflict={{ ...baseConflict, conflict_importance: 0.8, conflict_auto_resolve_at: undefined }}
        onResolve={mockResolve}
      />,
    );

    expect(screen.getByText(/High risk/)).toBeInTheDocument();
  });

  it('does not render high-risk badge when importance is missing', () => {
    render(
      <ConflictCard
        conflict={{ ...baseConflict, conflict_importance: undefined, conflict_auto_resolve_at: undefined }}
        onResolve={mockResolve}
      />,
    );

    expect(screen.queryByText(/High risk/)).not.toBeInTheDocument();
  });

  it('does not render high-risk badge for auto-resolving conflict even at high importance', () => {
    const inTenHours = new Date(FIXED_NOW.getTime() + 10 * 60 * 60 * 1000).toISOString();
    render(
      <ConflictCard
        conflict={{ ...baseConflict, conflict_importance: 0.95, conflict_auto_resolve_at: inTenHours }}
        onResolve={mockResolve}
      />,
    );

    expect(screen.queryByText(/High risk/)).not.toBeInTheDocument();
  });

  it('renders countdown for high-importance conflict that still has an auto-resolve deadline', () => {
    const inTenHours = new Date(FIXED_NOW.getTime() + 10 * 60 * 60 * 1000).toISOString();
    render(
      <ConflictCard
        conflict={{ ...baseConflict, conflict_importance: 0.95, conflict_auto_resolve_at: inTenHours }}
        onResolve={mockResolve}
      />,
    );

    expect(screen.getByText(/Auto-resolves in 10 hours/)).toBeInTheDocument();
  });

  it('renders minute-level countdown when deadline is under an hour away', () => {
    const inThirtyMinutes = new Date(FIXED_NOW.getTime() + 30 * 60 * 1000).toISOString();
    render(
      <ConflictCard
        conflict={{ ...baseConflict, conflict_importance: 0.7, conflict_auto_resolve_at: inThirtyMinutes }}
        onResolve={mockResolve}
      />,
    );

    expect(screen.getByText(/Auto-resolves in 30 min/)).toBeInTheDocument();
  });

  it('renders auto-resolving-soon text once the deadline has passed', () => {
    const pastDeadline = new Date(FIXED_NOW.getTime() - 60 * 1000).toISOString();
    render(
      <ConflictCard
        conflict={{ ...baseConflict, conflict_importance: 0.7, conflict_auto_resolve_at: pastDeadline }}
        onResolve={mockResolve}
      />,
    );

    expect(screen.getByText('Auto-resolving soon')).toBeInTheDocument();
  });

  it('renders episodic conflict with correct type icon', () => {
    render(
      <ConflictCard
        conflict={{ ...baseConflict, memory_type: 'episodic' }}
        onResolve={mockResolve}
      />,
    );

    expect(screen.getByText('Use New')).toBeInTheDocument();
    expect(screen.getByText('Keep Old')).toBeInTheDocument();
    expect(screen.getByText('Current Memory')).toBeInTheDocument();
    expect(screen.getByText('New Extracted Content')).toBeInTheDocument();
  });

  it('calls onResolve with keep_new when "Use New" is clicked', () => {
    render(
      <ConflictCard
        conflict={{ ...baseConflict, conflict_importance: 0.8, conflict_auto_resolve_at: undefined }}
        onResolve={mockResolve}
      />,
    );

    screen.getByText('Use New').click();
    expect(mockResolve).toHaveBeenCalledWith('conflict-1', 'keep_new', undefined);
  });
});
