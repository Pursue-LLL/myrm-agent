/**
 * Per-test setup shared by the compaction summary tests: seeds the chat store with a chat that has a summary and
 * resets the doubles from `compactedSummaryKit`. Kept apart from the kit because the mock factories import the
 * kit while the stores are still loading.
 */
import { afterEach, beforeEach, vi } from 'vitest';

import useChatStore from '@/store/useChatStore';
import useWorkspaceStore from '@/store/useWorkspaceStore';

import { kit } from './compactedSummaryKit';

export type ChatSeed = Partial<ReturnType<typeof useChatStore.getState>>;

/** Opens `chat-1` with a summary and a snapshot file, then applies `overrides`. */
export function seedChat(overrides: ChatSeed = {}): void {
  useChatStore.setState({
    chatId: 'chat-1',
    loading: false,
    compactedSummary: 'The summary',
    lastCompactionMeta: { tokensSaved: 1200, snapshotPath: '/snapshots/latest.json' },
    contextBranches: [],
    contextBranchesLoadError: null,
    ...overrides,
  });
}

/** Registers the reset every summary test file needs; call it once at the top level of the file. */
export function setUpSummaryTest(): void {
  const originalAddPane = useWorkspaceStore.getState().addPane;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    kit.addPane.mockReturnValue('pane');
    useWorkspaceStore.setState({ addPane: kit.addPane });
    seedChat();
  });

  afterEach(() => {
    delete window.__MYRM_E2E_API_BASE__;
    vi.unstubAllGlobals();
    useWorkspaceStore.setState({ addPane: originalAddPane });
    vi.restoreAllMocks();
  });
}
