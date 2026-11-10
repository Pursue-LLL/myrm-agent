import { act, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ForkInfoResponse } from '@/services/fork-api';
import { deferred } from '@/test-utils/deferred';

import { ParentChatLink } from '../ParentChatLink';

const hoisted = vi.hoisted(() => ({ getForkInfo: vi.fn() }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock('@/services/fork-api', () => ({ getForkInfo: (...args: unknown[]) => hoisted.getForkInfo(...args) }));

const forkInfo = (parent: string | null, forkPoint: number | null, success = true): ForkInfoResponse => ({
  success,
  data: { parent_chat_id: parent, fork_point: forkPoint, children: [] },
});

beforeEach(() => {
  vi.resetAllMocks();
  hoisted.getForkInfo.mockResolvedValue(forkInfo(null, null));
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

describe('ParentChatLink', () => {
  it('asks for the fork info of the chat it is given', async () => {
    hoisted.getForkInfo.mockResolvedValue(forkInfo(null, null));
    render(<ParentChatLink chatId="child-1" />);

    await vi.waitFor(() => expect(hoisted.getForkInfo).toHaveBeenCalledExactlyOnceWith('child-1'));
  });

  it('shows nothing until the fork info arrives', async () => {
    const pending = deferred<ForkInfoResponse>();
    hoisted.getForkInfo.mockReturnValue(pending.promise);
    const { container } = render(<ParentChatLink chatId="child-1" />);

    expect(container).toBeEmptyDOMElement();

    await act(async () => pending.resolve(forkInfo('parent-1', 2)));
    expect(screen.getByRole('link')).toBeInTheDocument();
  });

  it('links back to the parent and names the message the fork was made at, counting from 1', async () => {
    hoisted.getForkInfo.mockResolvedValue(forkInfo('parent-1', 0));
    const { rerender } = render(<ParentChatLink chatId="child-1" />);

    const link = await screen.findByRole('link', { name: 'Forked from parent conversation (from message #1)' });
    expect(link).toHaveAttribute('href', '/parent-1');

    hoisted.getForkInfo.mockResolvedValue(forkInfo('parent-9', 4));
    rerender(<ParentChatLink chatId="child-2" />);

    expect(await screen.findByRole('link', { name: /from message #5\)$/ })).toHaveAttribute('href', '/parent-9');
  });

  it('links without a message number when the fork point is unknown', async () => {
    hoisted.getForkInfo.mockResolvedValue(forkInfo('parent-1', null));
    render(<ParentChatLink chatId="child-1" />);

    expect(await screen.findByRole('link', { name: 'Forked from parent conversation' })).toHaveAttribute(
      'href',
      '/parent-1',
    );
  });

  it.each([
    ['a chat that is not a fork', forkInfo(null, null)],
    ['an answer that says it failed', forkInfo('parent-1', 1, false)],
  ])('shows nothing for %s', async (_label, response) => {
    hoisted.getForkInfo.mockResolvedValue(response);
    const { container } = render(<ParentChatLink chatId="child-1" />);

    await act(async () => undefined);

    expect(hoisted.getForkInfo).toHaveBeenCalledTimes(1);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows nothing when the fork info cannot be read, and logs why', async () => {
    const failure = new Error('offline');
    hoisted.getForkInfo.mockRejectedValue(failure);
    const { container } = render(<ParentChatLink chatId="child-1" />);

    await vi.waitFor(() => expect(console.error).toHaveBeenCalledWith('Failed to load fork info:', failure));
    expect(container).toBeEmptyDOMElement();
  });

  it('drops the link of the previous chat as soon as another chat is shown', async () => {
    hoisted.getForkInfo.mockResolvedValueOnce(forkInfo('parent-1', 3));
    const { rerender, container } = render(<ParentChatLink chatId="child-1" />);
    await screen.findByRole('link');
    const next = deferred<ForkInfoResponse>();
    hoisted.getForkInfo.mockReturnValue(next.promise);

    rerender(<ParentChatLink chatId="plain-chat" />);

    expect(container).toBeEmptyDOMElement();
    await act(async () => next.resolve(forkInfo(null, null)));
    expect(container).toBeEmptyDOMElement();
  });

  it('forgets the previous link when the next chat is not a fork or cannot be read', async () => {
    hoisted.getForkInfo.mockResolvedValueOnce(forkInfo('parent-1', 3));
    const { rerender, container } = render(<ParentChatLink chatId="child-1" />);
    await screen.findByRole('link');

    hoisted.getForkInfo.mockResolvedValueOnce(forkInfo(null, null));
    rerender(<ParentChatLink chatId="plain-1" />);
    await vi.waitFor(() => expect(hoisted.getForkInfo).toHaveBeenCalledTimes(2));
    rerender(<ParentChatLink chatId="child-1" />);
    expect(container).toBeEmptyDOMElement();

    hoisted.getForkInfo.mockRejectedValueOnce(new Error('offline'));
    rerender(<ParentChatLink chatId="plain-2" />);
    await vi.waitFor(() => expect(console.error).toHaveBeenCalled());
    rerender(<ParentChatLink chatId="child-1" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('ignores a late answer for a chat that is no longer shown', async () => {
    const first = deferred<ForkInfoResponse>();
    const second = deferred<ForkInfoResponse>();
    hoisted.getForkInfo.mockImplementation((id: string) => (id === 'child-1' ? first.promise : second.promise));
    const { rerender } = render(<ParentChatLink chatId="child-1" />);

    rerender(<ParentChatLink chatId="child-2" />);
    second.resolve(forkInfo('parent-2', 1));
    await screen.findByRole('link', { name: /message #2\)$/ });
    await act(async () => first.resolve(forkInfo('parent-1', 7)));

    expect(screen.getByRole('link')).toHaveAttribute('href', '/parent-2');
  });

  it('leaves the link of the current chat alone when a read for a chat that was left fails late', async () => {
    const first = deferred<ForkInfoResponse>();
    hoisted.getForkInfo.mockImplementation((id: string) =>
      id === 'child-1' ? first.promise : Promise.resolve(forkInfo('parent-2', 0)),
    );
    const { rerender } = render(<ParentChatLink chatId="child-1" />);

    rerender(<ParentChatLink chatId="child-2" />);
    await screen.findByRole('link');
    await act(async () => first.reject(new Error('late')));

    expect(screen.getByRole('link')).toHaveAttribute('href', '/parent-2');
    expect(console.error).toHaveBeenCalledExactlyOnceWith('Failed to load fork info:', expect.any(Error));
  });
});
