/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const mockFetchFollowUps = vi.fn();
const mockFetchAgents = vi.fn();

vi.mock('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => (key: string) => key,
}));

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock('@/store/useAgentStore', () => ({
  default: (selector: (state: { agents: { id: string; name: string }[]; fetchAgents: typeof mockFetchAgents }) => unknown) =>
    selector({
      agents: [{ id: 'agent-1', name: 'Work Assistant' }],
      fetchAgents: mockFetchAgents,
    }),
}));

vi.mock('@/services/followUps', () => ({
  fetchFollowUps: (...args: unknown[]) => mockFetchFollowUps(...args),
  dismissFollowUp: vi.fn(),
  snoozeFollowUp: vi.fn(),
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconHeart: () => <span data-testid="icon-heart" />,
}));

import FollowUpsPanel from '../sections/knowledge/FollowUpsPanel';

const sampleFollowUp = {
  id: 'cm_test_1',
  agent_id: 'agent-1',
  user_id: 'default',
  channel: 'web',
  kind: 'event_check_in' as const,
  sensitivity: 'personal' as const,
  status: 'pending' as const,
  reason: 'User mentioned an interview on Friday',
  suggested_text: 'How did the interview go?',
  dedupe_key: 'interview:2026-06-29',
  confidence: 0.9,
  due_earliest_ms: Date.now() + 3600_000,
  due_latest_ms: Date.now() + 7200_000,
  due_timezone: 'UTC',
  source_chat_id: 'chat-1',
  attempts: 0,
  created_at: '2026-06-29T10:00:00Z',
  snoozed_until_ms: null,
};

describe('FollowUpsPanel', () => {
  beforeEach(() => {
    mockFetchAgents.mockReset();
    mockFetchFollowUps.mockReset();
    mockFetchFollowUps.mockResolvedValue({ items: [sampleFollowUp], total: 1 });
  });

  it('loads and renders follow-up cards', async () => {
    render(<FollowUpsPanel />);

    await waitFor(() => {
      expect(screen.getByText('How did the interview go?')).toBeInTheDocument();
    });

    expect(mockFetchFollowUps).toHaveBeenCalled();
    expect(screen.getByText('User mentioned an interview on Friday')).toBeInTheDocument();
    expect(screen.getByText('snoozeAction')).toBeInTheDocument();
    expect(screen.getByText('dismissAction')).toBeInTheDocument();
  });

  it('shows empty state when no follow-ups exist', async () => {
    mockFetchFollowUps.mockResolvedValue({ items: [], total: 0 });

    render(<FollowUpsPanel />);

    await waitFor(() => {
      expect(screen.getByText('empty')).toBeInTheDocument();
    });
  });
});
