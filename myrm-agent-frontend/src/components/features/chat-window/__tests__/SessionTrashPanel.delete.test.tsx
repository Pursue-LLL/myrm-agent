import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { CascadeInfo } from '@/services/chatTrash';
import { deferred } from '@/test-utils/deferred';

import SessionTrashPanel from '../SessionTrashPanel';
import { kit, serveTrash, trashed, trashedChats } from './trashKit';

vi.mock('next-intl', async () => (await import('./trashKit')).nextIntlMock());
vi.mock('@/services/chatTrash', async () => (await import('./trashKit')).chatTrashServiceMock());
vi.mock('@/hooks/shared/useToast', async () => (await import('./trashKit')).toastHookMock());

const onCountChange = vi.fn<(count: number) => void>();

const titles = () => screen.queryAllByText(/^Chat c\d+$/).map((element) => element.textContent);
const dialog = () => screen.queryByRole('alertdialog');
const description = () => screen.getByRole('alertdialog').textContent ?? '';

async function click(element: HTMLElement): Promise<void> {
  await act(async () => {
    fireEvent.click(element);
  });
}

async function renderPanel(): Promise<void> {
  render(<SessionTrashPanel onCountChange={onCountChange} />);
  await act(async () => undefined);
}

/** Opens the permanent-delete confirmation of the `index`th row. */
const openDelete = (index: number) =>
  click(screen.getAllByRole('button', { name: 'permanentDelete' })[index] as HTMLElement);

const confirm = () => click(screen.getByTestId('confirm-dialog-confirm'));
const cancel = () => click(screen.getByTestId('confirm-dialog-cancel'));

beforeEach(() => {
  vi.resetAllMocks();
});

describe('SessionTrashPanel permanent deletion', () => {
  it('asks first, naming the chat, and deletes it only on confirmation', async () => {
    serveTrash(trashedChats(3));
    await renderPanel();
    onCountChange.mockClear();

    await openDelete(1);
    expect(description()).toContain('confirmDeleteTitle');
    expect(description()).toContain('confirmDeleteDesc {"title":"Chat c2"}');
    expect(kit.permanentlyDeleteChat).not.toHaveBeenCalled();
    await confirm();

    expect(kit.permanentlyDeleteChat).toHaveBeenCalledExactlyOnceWith('c2');
    expect(titles()).toEqual(['Chat c1', 'Chat c3']);
    expect(onCountChange).toHaveBeenCalledExactlyOnceWith(2);
    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'permanentlyDeleted', variant: 'default' });
    expect(dialog()).toBeNull();
  });

  it('leaves the chat alone when the question is cancelled', async () => {
    serveTrash(trashedChats(2));
    await renderPanel();

    await openDelete(0);
    await cancel();

    expect(kit.permanentlyDeleteChat).not.toHaveBeenCalled();
    expect(titles()).toEqual(['Chat c1', 'Chat c2']);
    expect(dialog()).toBeNull();
  });

  it('says so, and keeps the chat, when the deletion fails', async () => {
    serveTrash(trashedChats(2));
    await renderPanel();
    onCountChange.mockClear();
    kit.permanentlyDeleteChat.mockRejectedValueOnce(new Error('locked'));

    await openDelete(0);
    await confirm();

    expect(titles()).toEqual(['Chat c1', 'Chat c2']);
    expect(onCountChange).not.toHaveBeenCalled();
    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'deleteFailed', variant: 'destructive' });
  });

  it('lets a failed deletion be tried again', async () => {
    serveTrash(trashedChats(2));
    await renderPanel();
    kit.permanentlyDeleteChat.mockRejectedValueOnce(new Error('locked'));
    await openDelete(0);
    await confirm();

    await openDelete(0);
    await confirm();

    expect(kit.permanentlyDeleteChat).toHaveBeenCalledTimes(2);
    expect(titles()).toEqual(['Chat c2']);
  });

  it('does not delete a chat while it is being restored', async () => {
    serveTrash(trashedChats(2));
    await renderPanel();
    const restoring = deferred<void>();
    kit.restoreChat.mockReturnValueOnce(restoring.promise);
    await click(screen.getAllByRole('button', { name: 'restore' })[0] as HTMLElement);

    await openDelete(0);
    await confirm();

    expect(kit.permanentlyDeleteChat).not.toHaveBeenCalled();
    await act(async () => restoring.resolve());
    expect(titles()).toEqual(['Chat c2']);
  });

  it('names an untitled chat by its fallback', async () => {
    serveTrash([trashed('c1', { title: '' })]);
    await renderPanel();

    await openDelete(0);

    expect(description()).toContain('confirmDeleteDesc {"title":"untitled"}');
  });
});

describe('SessionTrashPanel cascade warning', () => {
  const info = (total: number): CascadeInfo => ({ counts: total ? { memories: total } : {}, total });

  it('warns how many associated items go with the chat', async () => {
    serveTrash(trashedChats(2));
    kit.getCascadeInfo.mockResolvedValue(info(3));
    await renderPanel();

    await openDelete(1);

    expect(kit.getCascadeInfo).toHaveBeenCalledExactlyOnceWith('c2');
    expect(description()).toContain('confirmDeleteDesc {"title":"Chat c2"}\ncascadeWarning {"count":3}');
  });

  it('adds nothing when nothing else goes with the chat', async () => {
    serveTrash(trashedChats(1));
    kit.getCascadeInfo.mockResolvedValue(info(0));
    await renderPanel();

    await openDelete(0);

    expect(description()).not.toContain('cascadeWarning');
  });

  it('still lets the user delete when the warning cannot be read', async () => {
    serveTrash(trashedChats(1));
    kit.getCascadeInfo.mockRejectedValue(new Error('offline'));
    await renderPanel();

    await openDelete(0);
    expect(description()).not.toContain('cascadeWarning');
    await confirm();

    expect(kit.permanentlyDeleteChat).toHaveBeenCalledExactlyOnceWith('c1');
  });

  it('reads the warning again each time the question opens, without showing the last one meanwhile', async () => {
    serveTrash(trashedChats(1));
    kit.getCascadeInfo.mockResolvedValueOnce(info(3));
    await renderPanel();
    await openDelete(0);
    expect(description()).toContain('cascadeWarning');
    await cancel();

    const pending = deferred<CascadeInfo>();
    kit.getCascadeInfo.mockReturnValueOnce(pending.promise);
    await openDelete(0);

    expect(kit.getCascadeInfo).toHaveBeenCalledTimes(2);
    expect(description()).not.toContain('cascadeWarning');
    await act(async () => pending.resolve(info(5)));
    expect(description()).toContain('cascadeWarning {"count":5}');
  });

  it('ignores a late answer for a chat whose question was closed', async () => {
    serveTrash(trashedChats(2));
    await renderPanel();
    const late = deferred<CascadeInfo>();
    kit.getCascadeInfo.mockReturnValueOnce(late.promise).mockResolvedValueOnce(info(1));
    await openDelete(0);
    await cancel();

    await openDelete(1);
    await act(async () => late.resolve(info(9)));

    expect(description()).toContain('confirmDeleteDesc {"title":"Chat c2"}\ncascadeWarning {"count":1}');
    expect(description()).not.toContain('"count":9');
  });
});

describe('SessionTrashPanel emptying', () => {
  const emptyAllButton = () => screen.getByRole('button', { name: /^emptyAll \(\d+\)$/ });

  it('asks first with the number of chats, then empties the trash and tells the parent', async () => {
    serveTrash(trashedChats(3));
    await renderPanel();
    onCountChange.mockClear();

    await click(emptyAllButton());
    expect(description()).toContain('confirmEmptyDesc {"count":3}');
    expect(kit.emptyTrash).not.toHaveBeenCalled();
    await confirm();

    expect(kit.emptyTrash).toHaveBeenCalledTimes(1);
    expect(titles()).toEqual([]);
    expect(screen.getByText('empty')).toBeInTheDocument();
    expect(onCountChange).toHaveBeenCalledExactlyOnceWith(0);
    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'emptied', variant: 'default' });
  });

  it('counts every chat in the trash, not only those on the screen', async () => {
    serveTrash(trashedChats(45));
    await renderPanel();

    expect(screen.getByRole('button', { name: 'emptyAll (45)' })).toBeInTheDocument();
    await click(emptyAllButton());

    expect(description()).toContain('confirmEmptyDesc {"count":45}');
  });

  it('does not read the server again for chats it just emptied, however many pages there were', async () => {
    serveTrash(trashedChats(45));
    await renderPanel();

    await click(emptyAllButton());
    await confirm();

    expect(screen.getByText('empty')).toBeInTheDocument();
    expect(kit.getTrashedChats).toHaveBeenCalledTimes(1);
  });

  it('keeps the list, and says so, when emptying fails', async () => {
    serveTrash(trashedChats(2));
    await renderPanel();
    onCountChange.mockClear();
    kit.emptyTrash.mockRejectedValueOnce(new Error('locked'));

    await click(emptyAllButton());
    await confirm();

    expect(titles()).toEqual(['Chat c1', 'Chat c2']);
    expect(onCountChange).not.toHaveBeenCalled();
    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'emptyFailed', variant: 'destructive' });
  });
});
