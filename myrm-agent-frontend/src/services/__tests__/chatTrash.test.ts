import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiRequest } from '@/lib/api';
import {
  TRASH_PAGE_SIZE,
  emptyTrash,
  getCascadeInfo,
  getTrashCount,
  getTrashedChats,
  permanentlyDeleteChat,
  restoreChat,
} from '../chatTrash';

vi.mock('@/lib/api', () => ({ apiRequest: vi.fn() }));

const api = vi.mocked(apiRequest);

beforeEach(() => {
  api.mockReset();
});

describe('chatTrash listing', () => {
  it('reads the first page by default, with the page size the panel counts pages in', async () => {
    api.mockResolvedValue({ items: [], pagination: { page: 1 } });

    await getTrashedChats();

    expect(TRASH_PAGE_SIZE).toBe(20);
    expect(api).toHaveBeenCalledExactlyOnceWith(`/chats/trash?page=1&page_size=${TRASH_PAGE_SIZE}`);
  });

  it('reads the page it is asked for, and hands back what the server answered', async () => {
    const answer = { items: [], pagination: { page: 3, has_next: false } };
    api.mockResolvedValue(answer);

    await expect(getTrashedChats(3)).resolves.toBe(answer);

    expect(api).toHaveBeenCalledExactlyOnceWith('/chats/trash?page=3&page_size=20');
  });

  it('reads the page size it is asked for', async () => {
    api.mockResolvedValue({ items: [], pagination: {} });

    await getTrashedChats(2, 5);

    expect(api).toHaveBeenCalledExactlyOnceWith('/chats/trash?page=2&page_size=5');
  });

  it('reads how many chats are in the trash', async () => {
    api.mockResolvedValue({ count: 7 });

    await expect(getTrashCount()).resolves.toBe(7);

    expect(api).toHaveBeenCalledExactlyOnceWith('/chats/trash/count');
  });

  it('reads what a permanent deletion would take along', async () => {
    const info = { counts: { tasks: 2 }, total: 2 };
    api.mockResolvedValue(info);

    await expect(getCascadeInfo('chat-1')).resolves.toBe(info);

    expect(api).toHaveBeenCalledExactlyOnceWith('/chats/trash/chat-1/cascade-info');
  });
});

describe('chatTrash actions', () => {
  it('restores a chat with a POST to its own address', async () => {
    api.mockResolvedValue(undefined);

    await restoreChat('chat-1');

    expect(api).toHaveBeenCalledExactlyOnceWith('/chats/trash/chat-1/restore', { method: 'POST' });
  });

  it('deletes a chat for good with a DELETE to its own address', async () => {
    api.mockResolvedValue(undefined);

    await permanentlyDeleteChat('chat-1');

    expect(api).toHaveBeenCalledExactlyOnceWith('/chats/trash/chat-1', { method: 'DELETE' });
  });

  it('empties the trash and says how many chats went', async () => {
    api.mockResolvedValue({ deleted_count: 4 });

    await expect(emptyTrash()).resolves.toBe(4);

    expect(api).toHaveBeenCalledExactlyOnceWith('/chats/trash', { method: 'DELETE' });
  });

  it('passes a failed request on to the caller', async () => {
    api.mockRejectedValue(new Error('offline'));

    await expect(restoreChat('chat-1')).rejects.toThrow('offline');
    await expect(getTrashedChats()).rejects.toThrow('offline');
  });
});
