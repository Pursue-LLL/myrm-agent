import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';

const MOCK_CONTENT = Array.from({ length: 20 }, (_, i) => {
  if (i === 3) return '$ npm install';
  if (i === 7) return 'Error: something failed here';
  if (i === 12) return 'warning: deprecated module found';
  if (i === 15) return 'Error: second error line';
  return `line ${i + 1} output`;
}).join('\n');

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}));

vi.mock('@/store/useChatStore', () => ({
  default: () => ({ chatId: 'test-chat' }),
}));

describe('EvictedOutputDrawer', () => {
  const onClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ content: MOCK_CONTENT }),
    });
  });

  async function renderDrawer() {
    const EvictedOutputDrawer = (await import('../EvictedOutputDrawer')).default;
    const result = render(
      <EvictedOutputDrawer filename="test.log" chatId="chat-1" onClose={onClose} />,
    );
    await waitFor(() => expect(screen.getByText(/line 1 output/)).toBeInTheDocument());
    return result;
  }

  describe('search navigation', () => {
    it('opens search bar with Ctrl+F and focuses input', async () => {
      await renderDrawer();
      act(() => {
        fireEvent.keyDown(document, { key: 'f', ctrlKey: true });
      });
      const input = screen.getByPlaceholderText('Search...');
      expect(input).toBeInTheDocument();
    });

    it('shows match count when searching', async () => {
      await renderDrawer();
      act(() => {
        fireEvent.keyDown(document, { key: 'f', ctrlKey: true });
      });
      const input = screen.getByPlaceholderText('Search...');
      await act(async () => {
        fireEvent.change(input, { target: { value: 'Error' } });
      });
      expect(screen.getByText('1/2')).toBeInTheDocument();
    });

    it('navigates to next match on Enter', async () => {
      await renderDrawer();
      act(() => {
        fireEvent.keyDown(document, { key: 'f', ctrlKey: true });
      });
      const input = screen.getByPlaceholderText('Search...');
      await act(async () => {
        fireEvent.change(input, { target: { value: 'Error' } });
      });
      expect(screen.getByText('1/2')).toBeInTheDocument();
      await act(async () => {
        fireEvent.keyDown(input, { key: 'Enter' });
      });
      expect(screen.getByText('2/2')).toBeInTheDocument();
    });

    it('navigates to previous match on Shift+Enter', async () => {
      await renderDrawer();
      act(() => {
        fireEvent.keyDown(document, { key: 'f', ctrlKey: true });
      });
      const input = screen.getByPlaceholderText('Search...');
      await act(async () => {
        fireEvent.change(input, { target: { value: 'Error' } });
      });
      await act(async () => {
        fireEvent.keyDown(input, { key: 'Enter' });
      });
      expect(screen.getByText('2/2')).toBeInTheDocument();
      await act(async () => {
        fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });
      });
      expect(screen.getByText('1/2')).toBeInTheDocument();
    });

    it('wraps around when navigating past last match', async () => {
      await renderDrawer();
      act(() => {
        fireEvent.keyDown(document, { key: 'f', ctrlKey: true });
      });
      const input = screen.getByPlaceholderText('Search...');
      await act(async () => {
        fireEvent.change(input, { target: { value: 'Error' } });
      });
      await act(async () => {
        fireEvent.keyDown(input, { key: 'Enter' });
      });
      await act(async () => {
        fireEvent.keyDown(input, { key: 'Enter' });
      });
      expect(screen.getByText('1/2')).toBeInTheDocument();
    });

    it('shows 0/0 when no matches found', async () => {
      await renderDrawer();
      act(() => {
        fireEvent.keyDown(document, { key: 'f', ctrlKey: true });
      });
      const input = screen.getByPlaceholderText('Search...');
      await act(async () => {
        fireEvent.change(input, { target: { value: 'nonexistent_xyz' } });
      });
      expect(screen.getByText('0/0')).toBeInTheDocument();
    });
  });

  describe('inline highlighting', () => {
    it('renders <mark> elements for matched text', async () => {
      await renderDrawer();
      act(() => {
        fireEvent.keyDown(document, { key: 'f', ctrlKey: true });
      });
      const input = screen.getByPlaceholderText('Search...');
      await act(async () => {
        fireEvent.change(input, { target: { value: 'Error' } });
      });
      const marks = document.querySelectorAll('mark');
      // "Error: something failed here" has 1 match, "Error: second error line" has 2 (case-insensitive)
      expect(marks.length).toBe(3);
    });

    it('highlights current match with orange and others with yellow', async () => {
      await renderDrawer();
      act(() => {
        fireEvent.keyDown(document, { key: 'f', ctrlKey: true });
      });
      const input = screen.getByPlaceholderText('Search...');
      await act(async () => {
        fireEvent.change(input, { target: { value: 'Error' } });
      });
      const marks = document.querySelectorAll('mark');
      const currentMark = marks[0];
      const otherMark = marks[1];
      expect(currentMark.className).toContain('bg-orange-400/50');
      expect(otherMark.className).toContain('bg-yellow-400/30');
    });
  });

  describe('Escape key behavior', () => {
    it('closes search bar on first Escape when search is visible', async () => {
      await renderDrawer();
      act(() => {
        fireEvent.keyDown(document, { key: 'f', ctrlKey: true });
      });
      expect(screen.getByPlaceholderText('Search...')).toBeInTheDocument();
      act(() => {
        fireEvent.keyDown(document, { key: 'Escape' });
      });
      expect(screen.queryByPlaceholderText('Search...')).not.toBeInTheDocument();
      expect(onClose).not.toHaveBeenCalled();
    });

    it('closes drawer on Escape when search is not visible', async () => {
      await renderDrawer();
      act(() => {
        fireEvent.keyDown(document, { key: 'Escape' });
      });
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('clears search term when closing search bar via Escape', async () => {
      await renderDrawer();
      act(() => {
        fireEvent.keyDown(document, { key: 'f', ctrlKey: true });
      });
      const input = screen.getByPlaceholderText('Search...');
      await act(async () => {
        fireEvent.change(input, { target: { value: 'Error' } });
      });
      expect(document.querySelectorAll('mark').length).toBe(3);
      act(() => {
        fireEvent.keyDown(document, { key: 'Escape' });
      });
      expect(document.querySelectorAll('mark').length).toBe(0);
    });

    it('requires two Escape presses to close drawer when search is open', async () => {
      await renderDrawer();
      act(() => {
        fireEvent.keyDown(document, { key: 'f', ctrlKey: true });
      });
      expect(screen.getByPlaceholderText('Search...')).toBeInTheDocument();
      act(() => {
        fireEvent.keyDown(document, { key: 'Escape' });
      });
      expect(onClose).not.toHaveBeenCalled();
      act(() => {
        fireEvent.keyDown(document, { key: 'Escape' });
      });
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  describe('loading states', () => {
    it('shows loading spinner initially', async () => {
      global.fetch = vi.fn().mockReturnValue(new Promise(() => {}));
      const EvictedOutputDrawer = (await import('../EvictedOutputDrawer')).default;
      render(
        <EvictedOutputDrawer filename="test.log" chatId="chat-1" onClose={onClose} />,
      );
      expect(screen.getByText('Loading full output...')).toBeInTheDocument();
    });

    it('shows expired state', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        json: () => Promise.resolve({ expired: true }),
      });
      const EvictedOutputDrawer = (await import('../EvictedOutputDrawer')).default;
      render(
        <EvictedOutputDrawer filename="test.log" chatId="chat-1" onClose={onClose} />,
      );
      await waitFor(() => expect(screen.getByText('Output Expired')).toBeInTheDocument());
    });

    it('shows error state on fetch failure', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        json: () => Promise.resolve({}),
      });
      const EvictedOutputDrawer = (await import('../EvictedOutputDrawer')).default;
      render(
        <EvictedOutputDrawer filename="test.log" chatId="chat-1" onClose={onClose} />,
      );
      await waitFor(() => expect(screen.getByText('Failed to load output')).toBeInTheDocument());
    });
  });

  describe('copy functionality', () => {
    it('copies content to clipboard on click', async () => {
      const writeText = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, { clipboard: { writeText } });
      await renderDrawer();
      const copyBtn = screen.getByTitle('Copy all');
      await act(async () => {
        fireEvent.click(copyBtn);
      });
      expect(writeText).toHaveBeenCalledWith(MOCK_CONTENT);
    });
  });
});
