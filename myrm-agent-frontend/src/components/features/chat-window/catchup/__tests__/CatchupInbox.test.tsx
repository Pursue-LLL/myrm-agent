/** @vitest-environment jsdom */

const getCatchupBriefs = vi.fn();
const markChatAsRead = vi.fn();
const push = vi.fn();
const chatState = { chatId: '' };

vi.mock('@/services/chat', () => ({
  getCatchupBriefs: (...args: unknown[]) => getCatchupBriefs(...args),
  markChatAsRead: (...args: unknown[]) => markChatAsRead(...args),
}));
vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: typeof chatState) => unknown) => selector(chatState),
}));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));
vi.mock('next-intl', async (importOriginal) => {
  const actual = await importOriginal<typeof import('next-intl')>();
  return { ...actual, useLocale: () => 'en' };
});

import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { CatchupBrief } from '@/services/chat';
import enMessages from '../../../../../../locales/en.json';
import { CatchupInbox } from '../CatchupInbox';

const brief = (chatId: string, overrides: Partial<CatchupBrief> = {}): CatchupBrief => ({
  chat_id: chatId,
  chat_title: `Chat ${chatId}`,
  updated_at: new Date().toISOString(),
  last_user_prompt: 'Question',
  result_preview: 'Answer',
  files_touched: [],
  tool_counts: {},
  needs_from_user: null,
  status: 'completed',
  ...overrides,
});

const digestEvent = (chatId: string, phase: string) =>
  window.dispatchEvent(new CustomEvent('run-digest-updated', { detail: { chat_id: chatId, digest: { phase } } }));

async function renderInbox() {
  const view = render(
    <NextIntlClientProvider locale="en" messages={{ Catchup: enMessages.Catchup }}>
      <CatchupInbox />
    </NextIntlClientProvider>,
  );
  await act(async () => {
    await Promise.resolve();
  });
  return view;
}

const advance = (ms: number) =>
  act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });

describe('CatchupInbox', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    getCatchupBriefs.mockReset();
    markChatAsRead.mockReset().mockResolvedValue(undefined);
    push.mockReset();
    chatState.chatId = '';
    getCatchupBriefs.mockResolvedValue({ briefs: [brief('a'), brief('b')] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('counts the chats the user has not caught up with, on an accessible trigger', async () => {
    await renderInbox();

    expect(screen.getByRole('button', { name: 'Catchup inbox, 2 waiting' })).toBeInTheDocument();
  });

  it('never lists the chat that is open', async () => {
    chatState.chatId = 'a';
    await renderInbox();

    expect(screen.getByRole('button', { name: 'Catchup inbox, 1 waiting' })).toBeInTheDocument();
  });

  it('renders nothing when the only unseen chat is the open one', async () => {
    getCatchupBriefs.mockResolvedValue({ briefs: [brief('a')] });
    chatState.chatId = 'a';
    const { container } = await renderInbox();

    expect(container).toBeEmptyDOMElement();
  });

  it('refetches once when a chat changes phase, not on every progress event', async () => {
    await renderInbox();
    expect(getCatchupBriefs).toHaveBeenCalledTimes(1);

    digestEvent('a', 'running');
    digestEvent('a', 'running');
    digestEvent('a', 'running');
    await advance(1100);
    expect(getCatchupBriefs).toHaveBeenCalledTimes(2);

    digestEvent('a', 'completed');
    await advance(1100);
    expect(getCatchupBriefs).toHaveBeenCalledTimes(3);
  });

  it('refetches after dismissing so an older chat can take the freed place', async () => {
    await renderInbox();
    fireEvent.click(screen.getByRole('button', { name: 'Catchup inbox, 2 waiting' }));

    await act(async () => {
      fireEvent.click(screen.getAllByRole('button', { name: 'Dismiss' })[0]);
    });
    await advance(1100);

    expect(markChatAsRead).toHaveBeenCalledWith('a');
    expect(getCatchupBriefs).toHaveBeenCalledTimes(2);
  });

  it('opens the chat after marking it read', async () => {
    await renderInbox();
    fireEvent.click(screen.getByRole('button', { name: 'Catchup inbox, 2 waiting' }));

    await act(async () => {
      fireEvent.click(screen.getAllByRole('button', { name: 'View Chat' })[1]);
    });

    expect(markChatAsRead).toHaveBeenCalledWith('b');
    expect(push).toHaveBeenCalledWith('/b');
  });
});
