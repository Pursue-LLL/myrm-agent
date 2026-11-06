import { render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { describe, expect, it, vi } from 'vitest';

import type { ChatItem } from '@/services/chat';
import { ChatHistoryRow, type ChatHistoryRowProps } from '../ChatHistoryRow';

vi.mock('next/link', () => ({
  default: ({ children, ...props }: ComponentProps<'a'>) => <a {...props}>{children}</a>,
}));
vi.mock('hugeicons-react', () => ({
  AiNetworkIcon: ({ className }: { className?: string }) => <span data-testid="agent-icon" className={className} />,
}));

const t = ((key: string) => key) as ChatHistoryRowProps['t'];

const chat: ChatItem = {
  id: 'chat-1',
  title: 'Quarterly review',
  firstMessage: 'first',
  lastMessage: 'last message text',
  updatedAt: new Date('2026-08-01T12:00:00Z'),
  createdAt: new Date('2026-08-01T10:00:00Z'),
  actionMode: 'agent',
  source: 'web',
};

const renderRow = (overrides: Partial<ChatHistoryRowProps> = {}) =>
  render(
    <ChatHistoryRow
      chat={chat}
      isMobile={false}
      isActive={false}
      renameId={null}
      renameValue=""
      exportingId={null}
      formatTime={() => 'three days ago'}
      onRename={vi.fn()}
      onRenameSubmit={vi.fn()}
      onRenameCancel={vi.fn()}
      onRenameValueChange={vi.fn()}
      onDelete={vi.fn()}
      onExport={vi.fn()}
      onPin={vi.fn()}
      onUnpin={vi.fn()}
      t={t}
      {...overrides}
    />,
  );

/** Text tinted by a black or white alpha, or set below 12px, drops under the contrast and size a list row needs. */
const expectLegible = (element: HTMLElement) => {
  expect(element.className).toContain('text-xs');
  expect(element.className).toContain('text-muted-foreground');
  expect(element.className).not.toMatch(/text-\[\d+px\]|text-(?:black|white)\/|dark:text-white\//);
};

describe.each([
  ['a pointer device', false],
  ['a phone', true],
])('ChatHistoryRow on %s', (_screen, isMobile) => {
  it('writes the last message and the time at 12px in the muted text color', () => {
    renderRow({ isMobile });

    expectLegible(screen.getByText('last message text'));
    expectLegible(screen.getByText('three days ago'));
  });

  it('draws the mode icon in the muted text color so it stays visible on both themes', () => {
    renderRow({ isMobile });

    const { className } = screen.getByTestId('agent-icon');
    expect(className).toContain('text-muted-foreground');
    expect(className).not.toMatch(/text-(?:black|white)\/|dark:text-white\//);
  });

  it('draws the more button in the muted text color', () => {
    renderRow({ isMobile });

    const icon = screen.getByRole('button', { name: 'common.more' }).querySelector('svg');
    expect(icon?.getAttribute('class')).toContain('text-muted-foreground');
  });
});

describe('ChatHistoryRow more button target', () => {
  it('is 32px on a pointer device', () => {
    renderRow({ isMobile: false });

    const { className } = screen.getByRole('button', { name: 'common.more' });
    expect(className).toContain('min-h-8');
    expect(className).toContain('min-w-8');
  });

  it('is a 44px finger target on a phone', () => {
    renderRow({ isMobile: true });

    const { className } = screen.getByRole('button', { name: 'common.more' });
    expect(className).toContain('min-h-11');
    expect(className).toContain('min-w-11');
  });
});
