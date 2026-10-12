/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ConversationOutline } from '../ConversationOutline';
import type { OutlineTurnItem } from '../outlineTypes';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, params?: Record<string, unknown>) => {
    if (params?.index !== undefined) {
      return `${key}:${params.index}`;
    }
    return key;
  },
}));

describe('ConversationOutline component', () => {
  const mockItems: OutlineTurnItem[] = [
    {
      turnIndex: 1,
      userMessageId: 'user-msg-01',
      assistantMessageId: 'asst-msg-01',
      promptPreview: 'Create a fullstack Todo application',
      replyPreview: 'Designed architecture and database schema',
      isLoaded: true,
      messageIndex: 0,
    },
    {
      turnIndex: 2,
      userMessageId: 'user-msg-02',
      assistantMessageId: 'asst-msg-02',
      promptPreview: 'Implement JWT authentication filter',
      replyPreview: 'Added OAuth2 and JWT middleware',
      isLoaded: true,
      messageIndex: 1,
    },
    {
      turnIndex: 3,
      userMessageId: 'user-msg-03',
      assistantMessageId: null,
      promptPreview: 'Run automated vitest suites',
      replyPreview: null,
      isLoaded: true,
      messageIndex: 2,
      isInFlight: true,
    },
  ];

  const defaultProps = {
    items: mockItems,
    activeViewportTurn: 2,
    onJumpToTurn: vi.fn(),
    isLoading: false,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders null when items count is less than 2', () => {
    const { container: c1 } = render(
      <ConversationOutline {...defaultProps} items={[]} />,
    );
    expect(c1.firstChild).toBeNull();

    const { container: c2 } = render(
      <ConversationOutline {...defaultProps} items={[mockItems[0]]} />,
    );
    expect(c2.firstChild).toBeNull();
  });

  it('renders navigation rail with outline ticks for each turn', () => {
    render(<ConversationOutline {...defaultProps} />);

    const nav = screen.getByRole('navigation', { name: 'ariaLabel' });
    expect(nav).toBeDefined();

    const ticks = screen.getAllByRole('button');
    expect(ticks).toHaveLength(3);

    // Turn 2 is the active viewport turn
    const turn2Btn = screen.getByRole('button', { name: 'jumpToTurn:2' });
    expect(turn2Btn.getAttribute('aria-current')).toBe('location');
    expect(screen.getByTestId('current-viewport-indicator')).toBeDefined();
  });

  it('displays tooltip card on mouse enter and hides on mouse leave', () => {
    render(<ConversationOutline {...defaultProps} />);

    // Hover over Turn 1
    const turn1Btn = screen.getByRole('button', { name: 'jumpToTurn:1' });
    fireEvent.mouseEnter(turn1Btn);

    const tooltip = screen.getByRole('tooltip');
    expect(tooltip).toBeDefined();
    expect(screen.getByText('Create a fullstack Todo application')).toBeDefined();
    expect(screen.getByText('Designed architecture and database schema')).toBeDefined();

    // Mouse leave track container
    const track = screen.getByTestId('outline-track-container');
    fireEvent.mouseLeave(track);

    expect(screen.queryByRole('tooltip')).toBeNull();
  });

  it('triggers onJumpToTurn when a tick is clicked', () => {
    render(<ConversationOutline {...defaultProps} />);

    const turn1Btn = screen.getByRole('button', { name: 'jumpToTurn:1' });
    fireEvent.click(turn1Btn);

    expect(defaultProps.onJumpToTurn).toHaveBeenCalledTimes(1);
    expect(defaultProps.onJumpToTurn).toHaveBeenCalledWith(mockItems[0]);
  });

  it('navigates through turns via Alt+ArrowUp and Alt+ArrowDown shortcuts', () => {
    render(<ConversationOutline {...defaultProps} />);

    // Active turn is 2. Alt+ArrowUp should jump to Turn 1
    fireEvent.keyDown(window, {
      key: 'ArrowUp',
      altKey: true,
    });
    expect(defaultProps.onJumpToTurn).toHaveBeenCalledWith(mockItems[0]);

    // Alt+ArrowDown should jump to Turn 3
    fireEvent.keyDown(window, {
      key: 'ArrowDown',
      altKey: true,
    });
    expect(defaultProps.onJumpToTurn).toHaveBeenCalledWith(mockItems[2]);
  });
});
