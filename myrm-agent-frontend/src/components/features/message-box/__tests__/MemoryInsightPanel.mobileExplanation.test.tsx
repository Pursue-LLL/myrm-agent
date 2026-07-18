import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { MemoryBriefStatus } from '@/store/chat/types';
import MemoryInsightPanel from '../MemoryInsightPanel';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/components/primitives/hover-card', () => ({
  HoverCard: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  HoverCardTrigger: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  HoverCardContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

describe('MemoryInsightPanel mobile explanation', () => {
  it('renders non-hover explanation text for skipped brief status', () => {
    const status: MemoryBriefStatus = {
      state: 'skipped',
      injection: { state: 'not_applied', reason: 'missing_context' },
    };
    render(<MemoryInsightPanel memoryBriefStatus={status} />);

    const descriptions = screen.getAllByText('briefUnavailableDescriptionNotInjected');
    expect(descriptions.length).toBeGreaterThanOrEqual(1);
    expect(descriptions.some((node) => node.className.includes('md:hidden'))).toBe(true);
  });
});
