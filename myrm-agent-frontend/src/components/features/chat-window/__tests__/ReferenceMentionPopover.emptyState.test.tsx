import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ReferenceMentionPopover } from '../ReferenceMentionPopover';

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: { chatId: string }) => unknown) => selector({ chatId: 'chat-1' }),
}));

vi.mock('@/components/primitives/popover', () => ({
  Popover: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverAnchor: () => null,
}));

// The translator is the global identity one, so a rendered key is the sentence that was chosen.
function renderWithNothingToList(query: string, searching: boolean) {
  return render(
    <ReferenceMentionPopover
      open
      results={[]}
      selectedIndex={0}
      query={query}
      searching={searching}
      onSelect={vi.fn()}
    />,
  );
}

describe('ReferenceMentionPopover with nothing to list', () => {
  it.each([
    ['a reference', 'src'],
    ['a prior conversation', 'chat:alpha'],
  ])('says it is searching while the answer for %s is on its way, not that nothing matched', (_name, query) => {
    renderWithNothingToList(query, true);

    expect(screen.getByText('searching')).toBeInTheDocument();
    expect(screen.queryByText('noResults')).toBeNull();
    expect(screen.queryByText('priorChatEmpty')).toBeNull();
  });

  it('tells what to type after a bare @chat:, where there is nothing to look up yet', () => {
    renderWithNothingToList('chat:', false);

    expect(screen.getByText('priorChatHint')).toBeInTheDocument();
    expect(screen.queryByText('priorChatEmpty')).toBeNull();
  });

  it('reports no matching conversation once a prior conversation search found nothing', () => {
    renderWithNothingToList('chat:alpha', false);

    expect(screen.getByText('priorChatEmpty')).toBeInTheDocument();
  });

  it('reports no matching reference once a search found nothing', () => {
    renderWithNothingToList('src', false);

    expect(screen.getByText('noResults')).toBeInTheDocument();
  });
});
