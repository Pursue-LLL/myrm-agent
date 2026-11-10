/**
 * Test kit for the compaction summary: the service, toast and router doubles that the summary state hook and the
 * summary view are driven through, plus the record builders both test files use.
 */
import { vi } from 'vitest';

import type { ArchivedChatMessage, BranchForkResult, ContextBranchRecord } from '@/services/chat';

const hoisted = vi.hoisted(() => {
  const push = vi.fn<(href: string) => void>();
  return {
    push,
    router: { push },
    createContextBranch: vi.fn<(chatId: string, payload: { snapshot_path: string }) => Promise<ContextBranchRecord>>(),
    forkContextBranch: vi.fn<(chatId: string, branchId: string, title?: string) => Promise<BranchForkResult>>(),
    getChatArchive: vi.fn<(chatId: string) => Promise<{ messages: ArchivedChatMessage[] }>>(),
    listContextBranches: vi.fn<(chatId: string) => Promise<ContextBranchRecord[]>>(),
    updateCompactionSummary: vi.fn<(chatId: string, summary: string) => Promise<void>>(),
    showI18nToast: vi.fn<(key: string, params: unknown, options: { type: string }) => void>(),
    addPane: vi.fn<(chatId?: string) => string>(),
    /** Renders the key, followed by its parameters when it has any, so a test can read both. */
    t: (key: string, params?: Record<string, unknown>) => (params ? `${key} ${JSON.stringify(params)}` : key),
  };
});
export { hoisted as kit };

export const navigationMock = () => ({ useRouter: () => hoisted.router });

export const nextIntlMock = () => ({ useTranslations: () => hoisted.t });

export async function chatServiceMock() {
  return {
    ...(await vi.importActual<typeof import('@/services/chat')>('@/services/chat')),
    createContextBranch: hoisted.createContextBranch,
    forkContextBranch: hoisted.forkContextBranch,
    getChatArchive: hoisted.getChatArchive,
    listContextBranches: hoisted.listContextBranches,
    updateCompactionSummary: hoisted.updateCompactionSummary,
  };
}

export async function toastServiceMock() {
  return {
    ...(await vi.importActual<typeof import('@/services/i18nToastService')>('@/services/i18nToastService')),
    showI18nToast: hoisted.showI18nToast,
  };
}

export const branch = (
  id: string,
  label = '',
  path = `/snapshots/${id}.json`,
  createdAt = '2026-01-02T03:04:05',
): ContextBranchRecord => ({
  branch_id: id,
  label,
  snapshot_path: path,
  created_at: createdAt,
});

export const archived = (id: string): ArchivedChatMessage => ({
  id,
  role: 'user',
  content: `message ${id}`,
  created_at: null,
});
