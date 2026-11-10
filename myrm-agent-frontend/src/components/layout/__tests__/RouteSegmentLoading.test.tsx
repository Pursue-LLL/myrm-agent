import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import RouteSegmentLoading from '../RouteSegmentLoading';

vi.mock('@/components/features/chat-window/MessageListSkeleton', () => ({
  default: () => <div data-testid="message-list-skeleton" />,
}));
vi.mock('@/components/features/settings/common/SettingsSkeleton', () => ({
  SettingsSkeleton: () => <div data-testid="settings-skeleton" />,
}));

describe('RouteSegmentLoading', () => {
  it('shows the message list skeleton for the chat segment, announced as busy', () => {
    render(<RouteSegmentLoading variant="chat" className="extra-class" />);

    const shell = screen.getByTestId('chat-route-loading');
    expect(shell).toHaveAttribute('aria-busy', 'true');
    expect(shell).toHaveAttribute('aria-live', 'polite');
    expect(shell).toHaveClass('extra-class', 'flex');
    expect(shell).toContainElement(screen.getByTestId('message-list-skeleton'));
    expect(screen.queryByTestId('settings-skeleton')).toBeNull();
  });

  it('shows the settings skeleton for the settings segment, announced as busy', () => {
    render(<RouteSegmentLoading variant="settings" className="extra-class" />);

    const shell = screen.getByTestId('settings-route-loading');
    expect(shell).toHaveAttribute('aria-busy', 'true');
    expect(shell).toHaveAttribute('aria-live', 'polite');
    expect(shell).toHaveClass('extra-class', 'flex');
    expect(shell).toContainElement(screen.getByTestId('settings-skeleton'));
    expect(screen.queryByTestId('message-list-skeleton')).toBeNull();
  });

  it.each([undefined, 'dashboard' as const])(
    'shows a heading and three cards of placeholders for variant %s',
    (variant) => {
      const { container } = render(<RouteSegmentLoading variant={variant} className="extra-class" />);

      const shell = container.firstElementChild;
      expect(shell).toHaveAttribute('aria-busy', 'true');
      expect(shell).toHaveAttribute('aria-live', 'polite');
      expect(shell).toHaveClass('extra-class', 'flex-col');
      expect(shell?.querySelectorAll('.animate-pulse')).toHaveLength(5);
      expect(screen.queryByTestId('chat-route-loading')).toBeNull();
      expect(screen.queryByTestId('settings-route-loading')).toBeNull();
      expect(screen.queryByTestId('message-list-skeleton')).toBeNull();
      expect(screen.queryByTestId('settings-skeleton')).toBeNull();
    },
  );
});
