import { act, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { TooltipProvider } from '@/components/primitives/tooltip';
import { deferred } from '@/test-utils/deferred';

import { ChatCronLink } from '../ChatCronLink';

const hoisted = vi.hoisted(() => ({ count: vi.fn() }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock('@/services/cron', () => ({ countChatCronJobs: (...args: unknown[]) => hoisted.count(...args) }));

const renderLink = (chatId: string) =>
  render(
    <TooltipProvider>
      <ChatCronLink chatId={chatId} />
    </TooltipProvider>,
  );
const rerenderLink = (view: ReturnType<typeof renderLink>, chatId: string) =>
  view.rerender(
    <TooltipProvider>
      <ChatCronLink chatId={chatId} />
    </TooltipProvider>,
  );

// Radix Tooltip positions itself with a ResizeObserver, which jsdom does not have.
beforeAll(() => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

afterAll(() => {
  vi.unstubAllGlobals();
});

beforeEach(() => {
  vi.resetAllMocks();
  hoisted.count.mockResolvedValue(0);
});

describe('ChatCronLink', () => {
  it('counts the tasks of the chat it is given', async () => {
    hoisted.count.mockResolvedValue(0);
    renderLink('chat-1');

    await vi.waitFor(() => expect(hoisted.count).toHaveBeenCalledExactlyOnceWith('chat-1'));
  });

  it('shows nothing until the count arrives', async () => {
    const pending = deferred<number>();
    hoisted.count.mockReturnValue(pending.promise);
    const { container } = renderLink('chat-1');

    expect(container).toBeEmptyDOMElement();

    await act(async () => pending.resolve(2));
    expect(screen.getByRole('link', { name: '2 scheduled' })).toBeInTheDocument();
  });

  it('links to the settings page filtered to the chat, with the id escaped', async () => {
    hoisted.count.mockResolvedValue(3);
    renderLink('chat/1&x');

    expect(await screen.findByRole('link', { name: '3 scheduled' })).toHaveAttribute(
      'href',
      '/settings/cron?chat_id=chat%2F1%26x',
    );
  });

  it('explains the badge on focus', async () => {
    hoisted.count.mockResolvedValue(1);
    renderLink('chat-1');

    fireEvent.focus(await screen.findByRole('link'));

    expect(await screen.findByRole('tooltip')).toHaveTextContent('View scheduled tasks linked to this conversation');
  });

  it('shows nothing for a chat without tasks or when the count cannot be read', async () => {
    hoisted.count.mockResolvedValueOnce(0).mockRejectedValueOnce(new Error('offline'));
    const view = renderLink('chat-1');
    await act(async () => undefined);
    expect(hoisted.count).toHaveBeenCalledTimes(1);
    expect(view.container).toBeEmptyDOMElement();

    rerenderLink(view, 'chat-2');
    await act(async () => undefined);

    expect(hoisted.count).toHaveBeenCalledTimes(2);
    expect(view.container).toBeEmptyDOMElement();
  });

  it('drops the count of the previous chat as soon as another chat is shown', async () => {
    hoisted.count.mockResolvedValueOnce(4);
    const view = renderLink('chat-1');
    await screen.findByRole('link');
    const next = deferred<number>();
    hoisted.count.mockReturnValue(next.promise);

    rerenderLink(view, 'chat-2');

    expect(view.container).toBeEmptyDOMElement();
    await act(async () => next.resolve(0));
    expect(view.container).toBeEmptyDOMElement();
  });

  it('forgets the previous count when the next chat cannot be read', async () => {
    hoisted.count.mockResolvedValueOnce(4);
    const view = renderLink('chat-1');
    await screen.findByRole('link');

    hoisted.count.mockRejectedValueOnce(new Error('offline'));
    rerenderLink(view, 'chat-2');
    await act(async () => undefined);
    expect(hoisted.count).toHaveBeenCalledTimes(2);
    rerenderLink(view, 'chat-1');

    expect(view.container).toBeEmptyDOMElement();
  });

  it('ignores a late answer for a chat that is no longer shown', async () => {
    const first = deferred<number>();
    hoisted.count.mockImplementation((id: string) => (id === 'chat-1' ? first.promise : Promise.resolve(2)));
    const view = renderLink('chat-1');

    rerenderLink(view, 'chat-2');
    await screen.findByRole('link', { name: '2 scheduled' });
    await act(async () => first.resolve(9));

    expect(screen.getByRole('link', { name: '2 scheduled' })).toBeInTheDocument();
  });

  it('ignores a late failure for a chat that is no longer shown', async () => {
    const first = deferred<number>();
    hoisted.count.mockImplementation((id: string) => (id === 'chat-1' ? first.promise : Promise.resolve(2)));
    const view = renderLink('chat-1');

    rerenderLink(view, 'chat-2');
    await screen.findByRole('link', { name: '2 scheduled' });
    await act(async () => first.reject(new Error('late')));

    expect(screen.getByRole('link', { name: '2 scheduled' })).toBeInTheDocument();
  });
});
