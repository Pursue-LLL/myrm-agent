/**
 * Test kit for the session trash panel: the service, toast and translation doubles, and a fake trash endpoint that
 * pages the way the real one does. Imported by the mock factories, so it must not pull in the component.
 */
import { vi } from 'vitest';

import type { CascadeInfo, TrashedChatItem, TrashedChatsResponse } from '@/services/chatTrash';

const hoisted = vi.hoisted(() => ({
  getTrashedChats: vi.fn<(page: number, pageSize?: number) => Promise<TrashedChatsResponse>>(),
  getCascadeInfo: vi.fn<(chatId: string) => Promise<CascadeInfo>>(),
  restoreChat: vi.fn<(chatId: string) => Promise<void>>(),
  permanentlyDeleteChat: vi.fn<(chatId: string) => Promise<void>>(),
  emptyTrash: vi.fn<() => Promise<number>>(),
  toast: vi.fn<(options: { title: string; variant?: string }) => void>(),
  /** Renders the key, followed by its parameters when it has any, so a test can read both. */
  t: (key: string, params?: Record<string, unknown>) => (params ? `${key} ${JSON.stringify(params)}` : key),
}));
export { hoisted as kit };

export const nextIntlMock = () => ({ useTranslations: () => hoisted.t });

export const toastHookMock = () => ({ toast: hoisted.toast });

export async function chatTrashServiceMock() {
  return {
    ...(await vi.importActual<typeof import('@/services/chatTrash')>('@/services/chatTrash')),
    getTrashedChats: hoisted.getTrashedChats,
    getCascadeInfo: hoisted.getCascadeInfo,
    restoreChat: hoisted.restoreChat,
    permanentlyDeleteChat: hoisted.permanentlyDeleteChat,
    emptyTrash: hoisted.emptyTrash,
  };
}

export const trashed = (id: string, overrides: Partial<TrashedChatItem> = {}): TrashedChatItem => ({
  id,
  title: `Chat ${id}`,
  firstMessage: '',
  lastMessage: '',
  actionMode: 'chat',
  source: 'web',
  updatedAt: new Date(0),
  createdAt: new Date(0),
  deletedAt: null,
  ...overrides,
});

/** `count` trashed chats `c1`..`cN`, newest first. */
export const trashedChats = (count: number): TrashedChatItem[] =>
  Array.from({ length: count }, (_, index) => trashed(`c${index + 1}`));

const SERVER_PAGE_SIZE = 20;

/**
 * Makes the service answer like the real endpoint: newest first, 20 to a page, read when the request is made.
 * Restoring or deleting a chat removes it on the "server", so later pages shift the way they do for real.
 */
export function serveTrash(initial: TrashedChatItem[]): { items: TrashedChatItem[] } {
  const server = { items: [...initial] };
  const remove = async (chatId: string): Promise<void> => {
    server.items = server.items.filter((item) => item.id !== chatId);
  };
  hoisted.getTrashedChats.mockImplementation(async (page, pageSize = SERVER_PAGE_SIZE) => {
    const start = (page - 1) * pageSize;
    const total = server.items.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    return {
      items: server.items.slice(start, start + pageSize),
      pagination: {
        page,
        page_size: pageSize,
        total,
        total_pages: totalPages,
        has_next: page < totalPages,
        has_prev: page > 1,
      },
    };
  });
  hoisted.restoreChat.mockImplementation(remove);
  hoisted.permanentlyDeleteChat.mockImplementation(remove);
  hoisted.emptyTrash.mockImplementation(async () => {
    const deleted = server.items.length;
    server.items = [];
    return deleted;
  });
  hoisted.getCascadeInfo.mockResolvedValue({ counts: {}, total: 0 });
  return server;
}
