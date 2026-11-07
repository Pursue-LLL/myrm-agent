import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import useChatStore from '@/store/useChatStore';
import ChatHistoryList from '../ChatHistoryList';

/** The list loads more through it; jsdom has none. */
class InertIntersectionObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

/** A modifier like `/80` lets the page show through the text and drops it under 4.5:1. */
const OPACITY_MODIFIER = /text-destructive[\w-]*\/\d+/;

describe('ChatHistoryList load error', () => {
  beforeEach(() => {
    vi.stubGlobal('IntersectionObserver', InertIntersectionObserver);
    // The list clears its error and reloads on mount, so the reload itself has to end in the failure.
    useChatStore.setState({
      loadChatHistory: vi.fn(async () => {
        useChatStore.setState({ chatHistoryItems: [], chatHistoryLoading: false, chatHistoryError: 'boom' });
      }),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('writes the message in the readable destructive text color at full strength', async () => {
    render(<ChatHistoryList isExpanded />);

    const { className } = await screen.findByText('common.loadHistoryError');
    expect(className).toContain('text-destructive-text');
    expect(className).not.toMatch(OPACITY_MODIFIER);
  });

  it('draws the icon in the same color at full strength', async () => {
    const { container } = render(<ChatHistoryList isExpanded />);

    await screen.findByText('common.loadHistoryError');
    const icon = container.querySelector('svg.text-destructive-text');
    expect(icon).not.toBeNull();
    expect(icon?.getAttribute('class')).not.toMatch(OPACITY_MODIFIER);
  });
});
