/** @vitest-environment jsdom */
import { render, screen, waitFor } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import useChatStore from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';
import en from '../../../../../locales/en.json';
import WorkingStateBadge from '../WorkingStateBadge';

const getWorkingState = vi.hoisted(() => vi.fn());

vi.mock('@/services/memory', () => ({ getWorkingState }));
vi.mock('next-intl', async (importOriginal) => importOriginal<typeof import('next-intl')>());

function renderBadge(chatId?: string) {
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      <WorkingStateBadge chatId={chatId} />
    </NextIntlClientProvider>,
  );
}

describe('WorkingStateBadge', () => {
  beforeEach(() => {
    getWorkingState.mockReset();
    useChatStore.setState({ incognitoMode: false, isMessagesLoaded: true });
    useConfigStore.setState({ enableMemory: true });
  });

  it('renders the persisted working state', async () => {
    getWorkingState.mockResolvedValue({
      content: 'Finish the release checklist',
      updated_at: null,
      ttl_days: 7,
      expired: false,
    });

    const { container } = renderBadge();

    expect(await screen.findByText('Working State')).toBeInTheDocument();
    expect(screen.getAllByText('Finish the release checklist').length).toBeGreaterThan(0);
    expect(container.querySelector('summary svg')).toHaveClass('group-open:rotate-180');
  });

  it('wraps long unbroken content in the expanded body', async () => {
    const longUrl = `https://example.com/${'a'.repeat(180)}`;
    getWorkingState.mockResolvedValue({
      content: longUrl,
      updated_at: null,
      ttl_days: 7,
      expired: false,
    });

    const { container } = renderBadge();

    await screen.findByText('Working State');
    const body = container.querySelector('p');
    expect(body).not.toBeNull();
    expect(body).toHaveClass('break-words');
    expect(body?.textContent).toBe(longUrl);
  });

  it('does not render expired or empty state', async () => {
    getWorkingState.mockResolvedValue({
      content: 'Old task',
      updated_at: null,
      ttl_days: 7,
      expired: true,
    });

    const { container } = renderBadge();

    await waitFor(() => expect(getWorkingState).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('does not read working state in incognito mode', () => {
    useChatStore.setState({ incognitoMode: true });

    const { container } = renderBadge();

    expect(container).toBeEmptyDOMElement();
    expect(getWorkingState).not.toHaveBeenCalled();
  });

  it('waits for chat hydration before reading a chat-scoped state', async () => {
    useChatStore.setState({ isMessagesLoaded: false });

    const { container } = renderBadge('chat-1');

    expect(container).toBeEmptyDOMElement();
    expect(getWorkingState).not.toHaveBeenCalled();

    useChatStore.setState({ isMessagesLoaded: true });
    await waitFor(() => expect(getWorkingState).toHaveBeenCalled());
  });

  it('does not read working state when memory is disabled', () => {
    useConfigStore.setState({ enableMemory: false });

    const { container } = renderBadge();

    expect(container).toBeEmptyDOMElement();
    expect(getWorkingState).not.toHaveBeenCalled();
  });
});
