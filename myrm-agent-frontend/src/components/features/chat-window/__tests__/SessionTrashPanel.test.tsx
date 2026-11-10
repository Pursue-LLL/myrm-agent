import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { TrashedChatsResponse } from '@/services/chatTrash';
import { deferred } from '@/test-utils/deferred';

import SessionTrashPanel from '../SessionTrashPanel';
import { kit, serveTrash, trashed, trashedChats } from './trashKit';

vi.mock('next-intl', async () => (await import('./trashKit')).nextIntlMock());
vi.mock('@/services/chatTrash', async () => (await import('./trashKit')).chatTrashServiceMock());
vi.mock('@/hooks/shared/useToast', async () => (await import('./trashKit')).toastHookMock());

const onRestored = vi.fn<() => void>();
const onCountChange = vi.fn<(count: number) => void>();

const restoreButtons = () => screen.queryAllByRole('button', { name: 'restore' });
const titles = () => screen.queryAllByText(/^Chat c\d+$/).map((element) => element.textContent);
const toastTitles = () => kit.toast.mock.calls.map(([options]) => options.title);

async function renderPanel(): Promise<void> {
  render(<SessionTrashPanel onRestored={onRestored} onCountChange={onCountChange} />);
  await act(async () => undefined);
}

async function click(element: HTMLElement): Promise<void> {
  await act(async () => {
    fireEvent.click(element);
  });
}

beforeEach(() => {
  vi.resetAllMocks();
});

describe('SessionTrashPanel listing', () => {
  it('shows progress until the first page arrives', async () => {
    const pending = deferred<TrashedChatsResponse>();
    kit.getTrashedChats.mockReturnValue(pending.promise);
    render(<SessionTrashPanel />);

    expect(screen.getByText('loading')).toBeInTheDocument();
    expect(screen.queryByText('empty')).not.toBeInTheDocument();
    await act(async () =>
      pending.resolve({
        items: [trashed('c1')],
        pagination: { page: 1, page_size: 20, total: 1, total_pages: 1, has_next: false, has_prev: false },
      }),
    );

    expect(screen.queryByText('loading')).not.toBeInTheDocument();
    expect(titles()).toEqual(['Chat c1']);
  });

  it('shows each chat with its title, last message and deletion time, and untitled chats by a fallback name', async () => {
    serveTrash([
      trashed('c1', { lastMessage: 'See you tomorrow', deletedAt: '2026-01-02T03:04:05Z' }),
      trashed('c2', { title: '' }),
    ]);

    await renderPanel();

    expect(screen.getByText('Chat c1')).toBeInTheDocument();
    expect(screen.getByText('See you tomorrow')).toBeInTheDocument();
    expect(screen.getByText(`deletedAt: ${new Date('2026-01-02T03:04:05Z').toLocaleString()}`)).toBeInTheDocument();
    expect(screen.getByText('untitled')).toBeInTheDocument();
    expect(screen.getAllByText(/^deletedAt:/)).toHaveLength(1);
  });

  it('tells the parent how many chats are in the trash', async () => {
    serveTrash(trashedChats(3));

    await renderPanel();

    expect(onCountChange).toHaveBeenCalledExactlyOnceWith(3);
    expect(screen.getByRole('button', { name: 'emptyAll (3)' })).toBeInTheDocument();
  });

  it('says the trash is empty only when it is', async () => {
    serveTrash([]);

    await renderPanel();

    expect(screen.getByText('empty')).toBeInTheDocument();
    expect(screen.getByText('emptyDesc')).toBeInTheDocument();
    expect(onCountChange).toHaveBeenCalledExactlyOnceWith(0);
  });
});

describe('SessionTrashPanel when the trash cannot be read', () => {
  it('does not claim the trash is empty, says so and offers a retry', async () => {
    kit.getTrashedChats.mockRejectedValueOnce(new Error('offline'));

    await renderPanel();

    expect(screen.queryByText('empty')).not.toBeInTheDocument();
    expect(screen.getByText('loadFailed')).toBeInTheDocument();
    expect(kit.toast).not.toHaveBeenCalled();
    expect(onCountChange).not.toHaveBeenCalled();

    serveTrash(trashedChats(2));
    await click(screen.getByRole('button', { name: 'retry' }));

    expect(screen.queryByText('loadFailed')).not.toBeInTheDocument();
    expect(titles()).toEqual(['Chat c1', 'Chat c2']);
  });

  it('shows progress while a retry is on its way', async () => {
    kit.getTrashedChats.mockRejectedValueOnce(new Error('offline'));
    await renderPanel();
    kit.getTrashedChats.mockReturnValueOnce(deferred<TrashedChatsResponse>().promise);

    await click(screen.getByRole('button', { name: 'retry' }));

    expect(screen.getByText('loading')).toBeInTheDocument();
    expect(screen.queryByText('loadFailed')).not.toBeInTheDocument();
  });

  it('keeps the page where it was when loading more fails, and asks for the same page again', async () => {
    serveTrash(trashedChats(25));
    await renderPanel();
    kit.getTrashedChats.mockRejectedValueOnce(new Error('offline'));

    await click(screen.getByRole('button', { name: 'loadMore' }));

    expect(toastTitles()).toEqual(['loadFailed']);
    expect(titles()).toHaveLength(20);
    expect(screen.getByRole('button', { name: 'loadMore' })).toBeEnabled();

    await click(screen.getByRole('button', { name: 'loadMore' }));

    expect(kit.getTrashedChats.mock.calls.map(([page]) => page)).toEqual([1, 2, 2]);
    expect(titles()).toHaveLength(25);
  });
});

describe('SessionTrashPanel restoring', () => {
  it('takes the chat out of the list, lowers the count and tells the parent and the user', async () => {
    serveTrash(trashedChats(3));
    await renderPanel();
    onCountChange.mockClear();

    await click(restoreButtons()[1] as HTMLElement);

    expect(kit.restoreChat).toHaveBeenCalledExactlyOnceWith('c2');
    expect(titles()).toEqual(['Chat c1', 'Chat c3']);
    expect(onCountChange).toHaveBeenCalledExactlyOnceWith(2);
    expect(screen.getByRole('button', { name: 'emptyAll (2)' })).toBeInTheDocument();
    expect(onRestored).toHaveBeenCalledTimes(1);
    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'restored', variant: 'default' });
  });

  it('keeps everything as it was, and says so, when the restore fails', async () => {
    serveTrash(trashedChats(2));
    await renderPanel();
    onCountChange.mockClear();
    kit.restoreChat.mockRejectedValueOnce(new Error('gone'));

    await click(restoreButtons()[0] as HTMLElement);

    expect(titles()).toEqual(['Chat c1', 'Chat c2']);
    expect(onCountChange).not.toHaveBeenCalled();
    expect(onRestored).not.toHaveBeenCalled();
    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'restoreFailed', variant: 'destructive' });
  });

  it('lets a failed restoration be tried again', async () => {
    serveTrash(trashedChats(2));
    await renderPanel();
    kit.restoreChat.mockRejectedValueOnce(new Error('gone'));

    await click(restoreButtons()[0] as HTMLElement);
    await click(restoreButtons()[0] as HTMLElement);

    expect(kit.restoreChat).toHaveBeenCalledTimes(2);
    expect(titles()).toEqual(['Chat c2']);
  });

  it('counts correctly when two chats are restored at once', async () => {
    serveTrash(trashedChats(4));
    await renderPanel();
    onCountChange.mockClear();
    const first = deferred<void>();
    const second = deferred<void>();
    kit.restoreChat.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);

    await click(restoreButtons()[0] as HTMLElement);
    await click(restoreButtons()[1] as HTMLElement);
    await act(async () => second.resolve());
    await act(async () => first.resolve());

    expect(titles()).toEqual(['Chat c3', 'Chat c4']);
    expect(onCountChange.mock.calls.map(([count]) => count)).toEqual([3, 2]);
  });

  it('asks the server once when the button is clicked twice', async () => {
    serveTrash(trashedChats(2));
    await renderPanel();
    const pending = deferred<void>();
    kit.restoreChat.mockReturnValueOnce(pending.promise);

    await click(restoreButtons()[0] as HTMLElement);
    await click(restoreButtons()[0] as HTMLElement);
    await act(async () => pending.resolve());

    expect(kit.restoreChat).toHaveBeenCalledTimes(1);
    expect(toastTitles()).toEqual(['restored']);
  });

  it('can tell a parent that re-renders on every count without React complaining', async () => {
    serveTrash(trashedChats(2));
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    function Parent() {
      const [count, setCount] = useState(-1);
      return (
        <>
          <span data-testid="badge">{count}</span>
          <SessionTrashPanel onCountChange={setCount} />
        </>
      );
    }
    render(<Parent />);
    await act(async () => undefined);
    expect(screen.getByTestId('badge')).toHaveTextContent('2');

    await click(restoreButtons()[0] as HTMLElement);

    expect(screen.getByTestId('badge')).toHaveTextContent('1');
    expect(consoleError).not.toHaveBeenCalled();
  });
});

describe('SessionTrashPanel paging', () => {
  it('offers more only while the server has more, and appends the next page', async () => {
    serveTrash(trashedChats(25));
    await renderPanel();
    expect(titles()).toHaveLength(20);

    const pending = deferred<TrashedChatsResponse>();
    kit.getTrashedChats.mockReturnValueOnce(pending.promise);
    await click(screen.getByRole('button', { name: 'loadMore' }));
    const busy = screen.getByRole('button', { name: 'loading' });
    expect(busy).toBeDisabled();
    expect(within(busy).queryByText('loadMore')).not.toBeInTheDocument();
    await act(async () =>
      pending.resolve({
        items: trashedChats(25).slice(20),
        pagination: { page: 2, page_size: 20, total: 25, total_pages: 2, has_next: false, has_prev: true },
      }),
    );

    expect(titles()).toHaveLength(25);
    expect(screen.queryByRole('button', { name: 'loadMore' })).not.toBeInTheDocument();
  });

  it('does not skip chats when some were restored before more are loaded', async () => {
    serveTrash(trashedChats(45));
    await renderPanel();
    for (const index of [0, 0, 0]) {
      await click(restoreButtons()[index] as HTMLElement);
    }
    expect(titles()).toHaveLength(17);

    await click(screen.getByRole('button', { name: 'loadMore' }));

    expect(titles()).toEqual(Array.from({ length: 20 }, (_, index) => `Chat c${index + 4}`));
    await click(screen.getByRole('button', { name: 'loadMore' }));

    expect(titles()).toEqual(Array.from({ length: 40 }, (_, index) => `Chat c${index + 4}`));
    expect(onCountChange).toHaveBeenLastCalledWith(42);
  });

  it('loads what is left instead of calling the trash empty when every loaded chat was restored', async () => {
    serveTrash(trashedChats(22));
    await renderPanel();
    for (let index = 0; index < 20; index += 1) {
      await click(restoreButtons()[0] as HTMLElement);
    }

    expect(screen.queryByText('empty')).not.toBeInTheDocument();
    expect(titles()).toEqual(['Chat c21', 'Chat c22']);
  });

  it('shows progress, never an empty trash, from the moment the last loaded chat is gone', async () => {
    serveTrash(trashedChats(22));
    await renderPanel();
    const serve = kit.getTrashedChats.getMockImplementation();
    if (!serve) {
      throw new Error('the trash is not served');
    }
    // What is on screen at the moment the next read starts.
    let shown = '';
    kit.getTrashedChats.mockImplementationOnce((page, pageSize) => {
      shown = document.body.textContent ?? '';
      return serve(page, pageSize);
    });

    for (let index = 0; index < 20; index += 1) {
      await click(restoreButtons()[0] as HTMLElement);
    }

    expect(shown).toContain('loading');
    expect(shown).not.toContain('empty');
  });

  it('does not read again and again when reading what is left fails', async () => {
    serveTrash(trashedChats(22));
    await renderPanel();
    // A failing read takes a tick, so a loop of retries could not starve the test of its own timers.
    kit.getTrashedChats.mockImplementation(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
      throw new Error('offline');
    });
    for (let index = 0; index < 20; index += 1) {
      await click(restoreButtons()[0] as HTMLElement);
    }
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30));
    });

    expect(screen.getByText('loadFailed')).toBeInTheDocument();
    expect(kit.getTrashedChats).toHaveBeenCalledTimes(2);
  });
});
