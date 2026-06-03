import React from 'react';
import { render, screen, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MessageToc } from '../MessageToc';

// Mock next-intl
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

// Mock IntersectionObserver
class MockIntersectionObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.IntersectionObserver = MockIntersectionObserver as any;

describe('MessageToc', () => {
  const mockContainerRef = {
    current: document.createElement('div'),
  } as React.RefObject<HTMLElement>;

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('should not render if there are less than 2 headings', () => {
    const { container } = render(
      <MessageToc content="# Only one heading" messageId="test-msg" containerRef={mockContainerRef} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('should render TOC items correctly', async () => {
    const markdown = `
# Heading 1
## Heading 2
### Heading 3
    `;
    render(<MessageToc content={markdown} messageId="test-msg" containerRef={mockContainerRef} />);

    // Wait for the unified parser to finish
    await waitFor(() => {
      // 3 headings * 2 (mobile and desktop TOCs) = 6
      expect(screen.getAllByText(/Heading/)).toHaveLength(6);
    });

    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(6);
    expect(links[0].getAttribute('href')).toBe('#toc-test-msg-0');
    expect(links[1].getAttribute('href')).toBe('#toc-test-msg-1');
    expect(links[2].getAttribute('href')).toBe('#toc-test-msg-2');
  });

  it('should debounce parsing when isStreaming is true', async () => {
    vi.useFakeTimers();
    const markdown = `
# Heading 1
## Heading 2
    `;
    render(<MessageToc content={markdown} messageId="test-msg" isStreaming={true} containerRef={mockContainerRef} />);

    // Initially, it should not render the headings because of the 500ms debounce
    expect(screen.queryByText('Heading 1')).toBeNull();

    // Fast-forward 500ms
    act(() => {
      vi.advanceTimersByTime(500);
    });

    // Restore real timers so Promises can resolve
    vi.useRealTimers();

    await waitFor(() => {
      expect(screen.getAllByText('Heading 1')).toHaveLength(2);
      expect(screen.getAllByText('Heading 2')).toHaveLength(2);
    });
  });

  it('should correctly parse raw HTML headings to match rehypeHeadingIds', async () => {
    const markdown = `
# Markdown Heading
<h1>HTML Heading</h1>
    `;
    render(<MessageToc content={markdown} messageId="test-msg" containerRef={mockContainerRef} />);

    await waitFor(() => {
      expect(screen.getAllByText('Markdown Heading')).toHaveLength(2);
      expect(screen.getAllByText('HTML Heading')).toHaveLength(2);
    });

    const links = screen.getAllByRole('link');
    expect(links[0].getAttribute('href')).toBe('#toc-test-msg-0');
    expect(links[1].getAttribute('href')).toBe('#toc-test-msg-1');
  });
});
