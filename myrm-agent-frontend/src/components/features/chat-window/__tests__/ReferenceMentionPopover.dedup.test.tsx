import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ReferenceMentionPopover } from '../ReferenceMentionPopover';
import { inSessionMentionDeduplicator } from '@/store/chat/inSessionMentionDeduplicator';
import type { ReferenceSuggestion } from '@/services/chat';

const mockChatId = 'test-session-123';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => {
    const translations: Record<string, string> = {
      title: 'Context Reference (@)',
      specialReferencesHint: 'Special References',
      alreadyInContext: 'In context',
      dedupNotice: 'This file is already injected in this session context',
      noResults: 'No matches found',
      priorChatEmpty: 'No prior conversations found',
      navigate: 'Navigate',
      select: 'Select',
      dismiss: 'Dismiss',
    };
    return translations[key] ?? key;
  },
}));

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: { chatId: string }) => unknown) => selector({ chatId: mockChatId }),
}));

vi.mock('@/components/primitives/popover', () => ({
  Popover: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverContent: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div className={className}>{children}</div>
  ),
  PopoverAnchor: () => null,
}));

describe('ReferenceMentionPopover deduplication and in-session indicators', () => {
  const sampleSuggestions: ReferenceSuggestion[] = [
    {
      source: 'workspace',
      reference_type: 'workspace_file',
      kind: 'file',
      label: 'src/main.ts',
      basename: 'src/main.ts',
      directory: 'src',
      relative_path: 'src/main.ts',
      file_id: 'f1',
      description: null,
      size: 1024,
      score_tier: 'exact',
      score: 1.0,
      match_ranges: [],
    },
    {
      source: 'workspace',
      reference_type: 'workspace_file',
      kind: 'file',
      label: 'src/utils.ts',
      basename: 'src/utils.ts',
      directory: 'src',
      relative_path: 'src/utils.ts',
      file_id: 'f2',
      description: null,
      size: 512,
      score_tier: 'exact',
      score: 1.0,
      match_ranges: [],
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    inSessionMentionDeduplicator.clearAll();
  });

  it('does not render popover when open is false', () => {
    const { container } = render(
      <ReferenceMentionPopover
        open={false}
        results={sampleSuggestions}
        selectedIndex={0}
        query=""
        onSelect={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders without [In context] badge when files have not been injected yet', () => {
    render(
      <ReferenceMentionPopover
        open={true}
        results={sampleSuggestions}
        selectedIndex={0}
        query=""
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getAllByText('src/main.ts').length).toBeGreaterThan(0);
    expect(screen.getAllByText('src/utils.ts').length).toBeGreaterThan(0);
    expect(screen.queryByTestId('mention-already-in-context')).toBeNull();
  });

  it('renders [In context] badge when a file has already been injected in current session', () => {
    // Pre-mark src/main.ts as injected in mockChatId session
    inSessionMentionDeduplicator.markInjected(mockChatId, ['src/main.ts'], 1);

    render(
      <ReferenceMentionPopover
        open={true}
        results={sampleSuggestions}
        selectedIndex={0}
        query=""
        onSelect={vi.fn()}
      />,
    );

    const dedupBadges = screen.getAllByTestId('mention-already-in-context');
    expect(dedupBadges.length).toBe(1);
    expect(dedupBadges[0].textContent).toContain('In context');
    expect(dedupBadges[0].getAttribute('title')).toBe(
      'This file is already injected in this session context',
    );
  });

  it('calls onSelect when clicking a suggestion item', () => {
    const handleSelect = vi.fn();
    render(
      <ReferenceMentionPopover
        open={true}
        results={sampleSuggestions}
        selectedIndex={0}
        query=""
        onSelect={handleSelect}
      />,
    );

    const items = screen.getAllByRole('button');
    // First suggestion item is the button for src/main.ts
    fireEvent.click(items[0]);
    expect(handleSelect).toHaveBeenCalledWith(sampleSuggestions[0]);
  });
});
