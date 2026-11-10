import { act, renderHook } from '@testing-library/react';
import type { useTranslations } from 'next-intl';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatItem } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { deferred } from '@/test-utils/deferred';

import { useChatActions } from '../useChatActions';

const kit = vi.hoisted(() => ({
  updateChatTitle: vi.fn<(chatId: string, title: string) => Promise<void>>(),
  deleteChat: vi.fn<(chatId: string) => Promise<void>>(),
  pinChat: vi.fn<(chatId: string) => Promise<{ isPinned: boolean; pinOrder: number }>>(),
  unpinChat: vi.fn<(chatId: string) => Promise<void>>(),
  restoreChat: vi.fn<(chatId: string) => Promise<void>>(),
  toast: vi.fn<(...args: unknown[]) => void>(),
}));

vi.mock('@/services/chat', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/chat')>()),
  updateChatTitle: kit.updateChatTitle,
  deleteChat: kit.deleteChat,
  pinChat: kit.pinChat,
  unpinChat: kit.unpinChat,
}));
vi.mock('@/services/chatTrash', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/chatTrash')>()),
  restoreChat: kit.restoreChat,
}));
vi.mock('@/hooks/shared/useToast', () => ({ toast: kit.toast }));

const t = ((key: string) => key) as unknown as ReturnType<typeof useTranslations>;

const makeChat = (id: string): ChatItem => ({
  id,
  title: `Title ${id}`,
  firstMessage: 'first',
  lastMessage: `Last ${id}`,
  updatedAt: new Date(),
  createdAt: new Date(),
  actionMode: 'agent',
  source: 'web',
});

const history = () => useChatStore.getState().chatHistoryItems;
const ids = () => history().map((chat) => chat.id);
const titles = () => history().map((chat) => `${chat.id}:${chat.title}`);

function seed(...chatIds: string[]): void {
  useChatStore.setState({ chatHistoryItems: chatIds.map(makeChat) });
}

/** Something else changes the history, like a new chat appearing, a reload or an infinite-scroll page. */
function changeHistory(update: (items: ChatItem[]) => ChatItem[]): void {
  act(() => useChatStore.setState({ chatHistoryItems: update(history()) }));
}

function renderActions() {
  return renderHook(() => useChatActions(t));
}

/** The undo button that the "moved to trash" notice offers. */
function undoButton(): () => void {
  const [, options] = kit.toast.mock.calls[0] as [string, { action: { onClick: () => void } }];
  return options.action.onClick;
}

const undoDeletion = () => undoButton()();

const flush = () => act(async () => new Promise<void>((resolve) => setTimeout(resolve, 0)));

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useChatActions renaming', () => {
  it('renames the chat in the history and leaves edit mode', async () => {
    seed('a', 'b');
    kit.updateChatTitle.mockResolvedValue(undefined);
    const { result } = renderActions();
    act(() => result.current.handleRename(makeChat('a')));
    expect(result.current.renameId).toBe('a');
    expect(result.current.renameValue).toBe('Title a');
    act(() => result.current.setRenameValue('Renamed'));

    await act(async () => result.current.handleRenameSubmit('a'));

    expect(kit.updateChatTitle).toHaveBeenCalledExactlyOnceWith('a', 'Renamed');
    expect(titles()).toEqual(['a:Renamed', 'b:Title b']);
    expect(result.current.renameId).toBeNull();
    expect(result.current.renameValue).toBe('');
  });

  it('keeps chats that arrived while the rename was in flight', async () => {
    seed('a', 'b');
    const pending = deferred<void>();
    kit.updateChatTitle.mockReturnValue(pending.promise);
    const { result } = renderActions();
    act(() => result.current.handleRename(makeChat('a')));
    act(() => result.current.setRenameValue('Renamed'));
    const submit = result.current.handleRenameSubmit;
    let submitted!: Promise<void>;
    act(() => {
      submitted = submit('a');
    });

    changeHistory((items) => [makeChat('new'), ...items]);
    await act(async () => {
      pending.resolve();
      await submitted;
    });

    expect(titles()).toEqual(['new:Title new', 'a:Renamed', 'b:Title b']);
  });

  it('does not bring back a chat that was deleted while the rename was in flight', async () => {
    seed('a', 'b');
    const pending = deferred<void>();
    kit.updateChatTitle.mockReturnValue(pending.promise);
    const { result } = renderActions();
    act(() => result.current.handleRename(makeChat('a')));
    act(() => result.current.setRenameValue('Renamed'));
    const submit = result.current.handleRenameSubmit;
    let submitted!: Promise<void>;
    act(() => {
      submitted = submit('a');
    });

    changeHistory((items) => items.filter((chat) => chat.id !== 'b'));
    await act(async () => {
      pending.resolve();
      await submitted;
    });

    expect(ids()).toEqual(['a']);
  });

  it('leaves the history alone, and edit mode, when the rename fails', async () => {
    seed('a', 'b');
    kit.updateChatTitle.mockRejectedValue(new Error('offline'));
    const { result } = renderActions();
    act(() => result.current.handleRename(makeChat('a')));
    act(() => result.current.setRenameValue('Renamed'));

    await act(async () => result.current.handleRenameSubmit('a'));

    expect(titles()).toEqual(['a:Title a', 'b:Title b']);
    expect(result.current.renameId).toBeNull();
    expect(result.current.renameValue).toBe('');
  });

  it('can be cancelled', () => {
    seed('a');
    const { result } = renderActions();
    act(() => result.current.handleRename(makeChat('a')));

    act(() => result.current.handleRenameCancel());

    expect(result.current.renameId).toBeNull();
    expect(result.current.renameValue).toBe('');
    expect(kit.updateChatTitle).not.toHaveBeenCalled();
  });
});

describe('useChatActions deleting', () => {
  it('moves the chat out of the history and offers to undo it', async () => {
    seed('a', 'b');
    kit.deleteChat.mockResolvedValue(undefined);
    const { result } = renderActions();
    act(() => result.current.handleDeleteClick('a'));

    await act(async () => result.current.handleDeleteConfirm());

    expect(kit.deleteChat).toHaveBeenCalledExactlyOnceWith('a');
    expect(ids()).toEqual(['b']);
    expect(kit.toast).toHaveBeenCalledExactlyOnceWith('chat.deleteChat.movedToTrash', {
      description: 'chat.deleteChat.undoHint',
      action: { label: 'chat.deleteChat.undo', onClick: expect.any(Function) },
    });
  });

  it('does nothing when no chat was picked for deletion', async () => {
    seed('a');
    const { result } = renderActions();

    await act(async () => result.current.handleDeleteConfirm());

    expect(kit.deleteChat).not.toHaveBeenCalled();
    expect(ids()).toEqual(['a']);
  });

  it('keeps chats that arrived while the deletion was in flight', async () => {
    seed('a', 'b');
    const pending = deferred<void>();
    kit.deleteChat.mockReturnValue(pending.promise);
    const { result } = renderActions();
    act(() => result.current.handleDeleteClick('a'));
    const confirm = result.current.handleDeleteConfirm;
    let confirmed!: Promise<void>;
    act(() => {
      confirmed = confirm();
    });

    changeHistory((items) => [makeChat('new'), ...items]);
    await act(async () => {
      pending.resolve();
      await confirmed;
    });

    expect(ids()).toEqual(['new', 'b']);
  });

  it('tells the user, keeps the history and passes the error on when the deletion fails', async () => {
    seed('a', 'b');
    kit.deleteChat.mockRejectedValue(new Error('server said no'));
    const { result } = renderActions();
    act(() => result.current.handleDeleteClick('a'));

    await expect(act(async () => result.current.handleDeleteConfirm())).rejects.toThrow('server said no');

    expect(ids()).toEqual(['a', 'b']);
    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({
      title: 'chat.deleteChat.error',
      description: 'server said no',
      variant: 'destructive',
    });
  });

  describe('undoing a deletion', () => {
    async function deleteFirstChat() {
      seed('a', 'b');
      kit.deleteChat.mockResolvedValue(undefined);
      const view = renderActions();
      act(() => view.result.current.handleDeleteClick('a'));
      await act(async () => view.result.current.handleDeleteConfirm());
      return view;
    }

    it('puts the chat back at the top', async () => {
      await deleteFirstChat();
      kit.restoreChat.mockResolvedValue(undefined);

      undoDeletion();
      await flush();

      expect(kit.restoreChat).toHaveBeenCalledExactlyOnceWith('a');
      expect(ids()).toEqual(['a', 'b']);
    });

    it('does not discard what changed in the history since the deletion', async () => {
      await deleteFirstChat();
      kit.restoreChat.mockResolvedValue(undefined);
      changeHistory((items) => [makeChat('new'), ...items]);

      undoDeletion();
      await flush();

      expect(ids()).toEqual(['a', 'new', 'b']);
    });

    it('does not add the chat twice when a reload has already brought it back', async () => {
      await deleteFirstChat();
      kit.restoreChat.mockResolvedValue(undefined);
      changeHistory((items) => [makeChat('c'), makeChat('a'), ...items]);

      undoDeletion();
      await flush();

      expect(ids()).toEqual(['c', 'a', 'b']);
    });

    it('tells the user and keeps the history when the chat cannot be restored', async () => {
      await deleteFirstChat();
      kit.restoreChat.mockRejectedValue(new Error('gone'));
      const undo = undoButton();
      kit.toast.mockClear();

      undo();
      await flush();

      expect(ids()).toEqual(['b']);
      expect(kit.toast).toHaveBeenCalledExactlyOnceWith({
        title: 'chat.deleteChat.undoFailed',
        variant: 'destructive',
      });
    });
  });
});

describe('useChatActions pinning', () => {
  it('pins the chat in the history', async () => {
    seed('a', 'b');
    kit.pinChat.mockResolvedValue({ isPinned: true, pinOrder: 3 });
    const { result } = renderActions();

    await act(async () => result.current.handlePin('a'));

    expect(kit.pinChat).toHaveBeenCalledExactlyOnceWith('a');
    expect(history().map((chat) => [chat.id, chat.isPinned, chat.pinOrder])).toEqual([
      ['a', true, 3],
      ['b', undefined, undefined],
    ]);
  });

  it('unpins the chat in the history', async () => {
    useChatStore.setState({ chatHistoryItems: [{ ...makeChat('a'), isPinned: true, pinOrder: 2 }, makeChat('b')] });
    kit.unpinChat.mockResolvedValue(undefined);
    const { result } = renderActions();

    await act(async () => result.current.handleUnpin('a'));

    expect(kit.unpinChat).toHaveBeenCalledExactlyOnceWith('a');
    expect(history().map((chat) => [chat.id, chat.isPinned, chat.pinOrder])).toEqual([
      ['a', false, 0],
      ['b', undefined, undefined],
    ]);
  });

  it('tells the user why a pin failed and leaves the history as it was', async () => {
    seed('a');
    kit.pinChat.mockRejectedValue(new Error('offline'));
    const { result } = renderActions();

    await act(async () => result.current.handlePin('a'));

    expect(history()[0].isPinned).toBeUndefined();
    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({
      title: 'chat.pin.error',
      description: 'offline',
      variant: 'destructive',
    });
  });

  it('tells the user why an unpin failed, and says unknown for anything that is not an error', async () => {
    useChatStore.setState({ chatHistoryItems: [{ ...makeChat('a'), isPinned: true, pinOrder: 1 }] });
    kit.unpinChat.mockRejectedValue('nope');
    const { result } = renderActions();

    await act(async () => result.current.handleUnpin('a'));

    expect(history()[0].isPinned).toBe(true);
    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({
      title: 'chat.unpin.error',
      description: 'common.unknownError',
      variant: 'destructive',
    });
  });
});
