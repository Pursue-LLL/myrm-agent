/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock('@/components/primitives/button', () => ({
  Button: ({ children, ...rest }: { children: React.ReactNode }) => <button {...rest}>{children}</button>,
}));

vi.mock('@/components/primitives/badge', () => ({
  Badge: ({ children, ...rest }: { children: React.ReactNode }) => <span {...rest}>{children}</span>,
}));

vi.mock('@/components/primitives/card', () => ({
  Card: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconBook: () => <span data-testid="icon-book" />,
  IconEdit: () => <span data-testid="icon-edit" />,
  IconLoader: () => <span data-testid="icon-loader" />,
  IconSave: () => <span data-testid="icon-save" />,
  IconX: () => <span data-testid="icon-x" />,
}));

vi.mock('@/components/features/message-box/MarkdownContent', () => ({
  default: () => <div data-testid="markdown-content" />,
}));

vi.mock('@/lib/wiki/claimStatusDisplay', () => ({
  claimStatusClass: () => 'status-class',
  claimStatusLabel: (_status: string, labels: Record<string, string>) => labels.supported ?? 'supported',
  formatClaimConfidence: () => '85%',
  shouldShowClaimConfidence: () => false,
}));

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: Array<string | false | null | undefined>) => args.filter(Boolean).join(' '),
}));

import { WikiConceptDetailPanel } from '../WikiConceptDetailPanel';
import type { Concept } from '@/services/wikiService';

const baseProps = {
  selectedConcept: null,
  isEditing: false,
  editTab: 'truth' as const,
  editContent: '',
  editCompiledTruth: '',
  editTimelineDisplay: '',
  editTimelineAppend: '',
  editTags: '',
  editAliases: '',
  isSaving: false,
  onEdit: () => {},
  onCancelEdit: () => {},
  onSave: () => {},
  onEditTabChange: () => {},
  onEditContentChange: () => {},
  onEditCompiledTruthChange: () => {},
  onEditTimelineAppendChange: () => {},
  onEditTagsChange: () => {},
  onEditAliasesChange: () => {},
};

describe('WikiConceptDetailPanel source provenance jump', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('links to message-level deep jump when source_message is present', () => {
    const concept: Concept = {
      name: 'Alpha',
      content: '# Alpha',
      provenance: 'chat_compound',
      source_chat: 'chat-123',
      source_message: 'msg-456',
    };
    render(<WikiConceptDetailPanel {...baseProps} selectedConcept={concept} />);
    const link = screen.getByText('sourceChat') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe('/chat-123?highlight=msg-456');
  });

  it('falls back to chat-level link when source_message is absent', () => {
    const concept: Concept = {
      name: 'Alpha',
      content: '# Alpha',
      source_chat: 'chat-123',
      source_message: null,
    };
    render(<WikiConceptDetailPanel {...baseProps} selectedConcept={concept} />);
    const link = screen.getByText('sourceChat') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe('/chat-123');
  });

  it('renders no provenance link when source_chat is absent', () => {
    const concept: Concept = {
      name: 'Alpha',
      content: '# Alpha',
      source_chat: null,
      source_message: null,
    };
    render(<WikiConceptDetailPanel {...baseProps} selectedConcept={concept} />);
    expect(screen.queryByText('sourceChat')).toBeNull();
  });
});
