import { act, fireEvent, render, screen, type RenderResult } from '@testing-library/react';
import { useSyncExternalStore, type ComponentType } from 'react';
import { vi, type Mock } from 'vitest';

import type { Memory, MemoryPaginationInfo, MemorySortBy, MemorySortOrder, MemoryType } from '@/services/memory';
import { settle } from '@/test-utils/fakeClock';
import MemorySection from '../../MemorySection';
import { confirmOf, dryRunOf } from './memorySectionFixtures';

/**
 * 记忆面板测试共用工具：模块 mock（须在被测面板之前 import 本文件才会生效）、可变夹具状态、渲染与交互 helper。
 * store / 接口 / 提示 / 子组件全部在此替换，测试只断言面板的可见行为、对接口与 store 的调用和弹出的提示。
 */

interface MemoryStoreState {
  pendingCount: number;
  memories: Memory[];
  memoriesLoading: boolean;
  memoryPagination: MemoryPaginationInfo | null;
  memoryTypeFilter: MemoryType | null;
  memoryTagFilter: string | null;
  memorySearchQuery: string;
  memorySortBy: MemorySortBy;
  memorySortOrder: MemorySortOrder;
  archivedMemories: Memory[];
  archivedLoading: boolean;
  archivedPagination: MemoryPaginationInfo | null;
}

interface World {
  auth: { user: { id: string } | null; isInitialized: boolean };
  config: Record<string, boolean | number | Mock>;
  retrieval: { embeddingApplied: boolean; checkOrphanCollections: Mock };
  labsEnabled: boolean;
  search: URLSearchParams;
}

const hoisted = vi.hoisted(() => {
  const defaults: MemoryStoreState = {
    pendingCount: 0,
    memories: [],
    memoriesLoading: false,
    memoryPagination: null,
    memoryTypeFilter: null,
    memoryTagFilter: null,
    memorySearchQuery: '',
    memorySortBy: 'created_at',
    memorySortOrder: 'desc',
    archivedMemories: [],
    archivedLoading: false,
    archivedPagination: null,
  };
  const listeners = new Set<() => void>();
  const patch = (partial: Partial<MemoryStoreState>) => {
    snapshot = { ...snapshot, ...partial };
    listeners.forEach((listener) => listener());
  };
  const actions = {
    fetchPendingMemories: vi.fn(),
    fetchMemories: vi.fn(),
    loadMoreMemories: vi.fn(),
    fetchArchivedMemories: vi.fn(),
    deleteMemory: vi.fn(),
    deleteAllMemories: vi.fn(),
    restoreMemory: vi.fn(),
    purgeMemory: vi.fn(),
    setMemoryTypeFilter: vi.fn((value: MemoryType | null) => patch({ memoryTypeFilter: value })),
    setMemoryTagFilter: vi.fn((value: string | null) => patch({ memoryTagFilter: value })),
    setMemorySearchQuery: vi.fn((value: string) => patch({ memorySearchQuery: value })),
    setMemorySortBy: vi.fn((value: MemorySortBy) => patch({ memorySortBy: value })),
    setMemorySortOrder: vi.fn((value: MemorySortOrder) => patch({ memorySortOrder: value })),
  };
  let snapshot = { ...defaults, ...actions };
  const push = vi.fn();
  return {
    actions,
    loadStubs: () => import('./memorySectionStubs'),
    patch,
    push,
    router: { push },
    reset: () => {
      snapshot = { ...defaults, ...actions };
    },
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    getSnapshot: () => snapshot,
    world: {} as World,
    // Interpolation values are kept in the output so tests can assert them.
    translate: Object.assign(
      (key: string, values?: Record<string, unknown>) => (values ? `${key}|${JSON.stringify(values)}` : key),
      { has: () => true },
    ),
    setInputMessage: vi.fn(),
    toast: vi.fn(),
    actionToastInfo: vi.fn(),
    service: {
      restoreMemory: vi.fn(),
      exportMemories: vi.fn(),
      exportMemoriesMarkdown: vi.fn(),
      updateMemory: vi.fn(),
      updateMemoryStatus: vi.fn(),
      getMemoryTags: vi.fn(),
    },
    archive: { dryRunImportMemories: vi.fn(), confirmImportMemories: vi.fn() },
  };
});

vi.mock('next-intl', () => ({ useTranslations: () => hoisted.translate, useLocale: () => 'en' }));
vi.mock('next/navigation', () => ({
  useRouter: () => hoisted.router,
  useSearchParams: () => hoisted.world.search,
}));
vi.mock('@/store/useConfigStore', () => ({ default: () => hoisted.world.config }));
vi.mock('@/store/useAuthStore', () => ({ default: () => hoisted.world.auth }));
vi.mock('@/store/useRetrievalStore', () => ({
  default: (select: (state: World['retrieval']) => unknown) => select(hoisted.world.retrieval),
}));
vi.mock('@/store/useChatStore', () => ({
  default: Object.assign(() => ({}), { getState: () => ({ setInputMessage: hoisted.setInputMessage }) }),
}));
vi.mock('@/store/memory', () => ({
  useMemoryStore: (select?: (state: ReturnType<typeof hoisted.getSnapshot>) => unknown) => {
    const state = useSyncExternalStore(hoisted.subscribe, hoisted.getSnapshot);
    return select ? select(state) : state;
  },
}));
vi.mock('@/services/memory', () => hoisted.service);
vi.mock('@/services/memory/archive', () => hoisted.archive);
vi.mock('@/hooks/shared/useToast', () => ({ toast: hoisted.toast }));
vi.mock('@/lib/utils/toast', () => ({ toast: { info: hoisted.actionToastInfo } }));
vi.mock('@/lib/memory/memoryLabs', () => ({ isMemoryLabsEnabled: () => hoisted.world.labsEnabled }));
vi.mock('@/components/primitives/tooltip', async () => {
  const { Passthrough, TooltipBody } = await hoisted.loadStubs();
  return { Tooltip: Passthrough, TooltipTrigger: Passthrough, TooltipContent: TooltipBody };
});
vi.mock('@/components/features/app-shell/login-prompt', async () => ({
  default: (await hoisted.loadStubs()).LoginPromptStub,
}));
vi.mock('@/components/features/memory/dialogs/MemoryClearAllDialog', async () => ({
  default: (await hoisted.loadStubs()).ClearAllDialog,
}));
vi.mock('@/components/features/memory/settings/MemorySettingsToggles', async () => ({
  default: (await hoisted.loadStubs()).SettingsToggles,
}));
vi.mock('@/components/features/memory/settings/MemoryTabSwitcher', async () => ({
  default: (await hoisted.loadStubs()).TabSwitcher,
}));
vi.mock('@/components/features/memory/pending/PendingMemoryList', async () => ({
  default: (await hoisted.loadStubs()).PendingList,
}));
vi.mock('@/components/features/memory/cards/MemoryCard', async () => ({
  default: (await hoisted.loadStubs()).MemoryCardStub,
}));
vi.mock('@/components/features/memory/cards/MemoryTypeIcon', async () => ({
  default: (await hoisted.loadStubs()).TypeIcon,
}));
vi.mock('@/components/features/memory/settings/MemoryTrashPanel', async () => ({
  default: (await hoisted.loadStubs()).TrashPanel,
}));
vi.mock('@/components/features/memory/dialogs/MemoryEditDialog', async () => ({
  default: (await hoisted.loadStubs()).memoryDialog('edit-dialog'),
}));
vi.mock('@/components/features/memory/cards/MemoryDetailSheet', async () => ({
  default: (await hoisted.loadStubs()).memoryDialog('detail-sheet'),
}));
vi.mock('@/components/features/memory/dialogs/MemoryCreateDialog', async () => ({
  default: (await hoisted.loadStubs()).openFlagDialog('create-dialog'),
}));
vi.mock('@/components/features/memory/guides/MemoryGuide', async () => ({
  default: (await hoisted.loadStubs()).openFlagDialog('guide'),
}));
vi.mock('@/components/features/memory/dialogs/ShareRulesDialog', async () => ({
  default: (await hoisted.loadStubs()).openFlagDialog('share-rules'),
}));
vi.mock('@/components/features/memory/dialogs/MemoryImportReviewDialog', async () => ({
  MemoryImportReviewDialog: (await hoisted.loadStubs()).ImportReviewDialog,
}));
vi.mock('@/components/features/memory/mesh', async () => ({
  MemoryDomainMeshPanel: (await hoisted.loadStubs()).marker('domain-mesh'),
}));
vi.mock('@/components/features/memory/cards/MemoryStats', async () => ({
  default: (await hoisted.loadStubs()).marker('memory-stats'),
}));
vi.mock('@/components/features/memory/command-center/MemoryCommandCenter', async () => ({
  default: (await hoisted.loadStubs()).marker('command-center'),
}));
vi.mock('@/components/features/memory/cards/TasteSummaryCard', async () => ({
  default: (await hoisted.loadStubs()).marker('taste-summary'),
}));
vi.mock('@/components/features/memory/cards/PreferenceStabilityCard', async () => ({
  default: (await hoisted.loadStubs()).marker('preference-stability'),
}));
vi.mock('@/components/features/memory/shared-context/SharedContextPanel', async () => ({
  default: (await hoisted.loadStubs()).marker('shared-context'),
}));
vi.mock('@/components/features/memory/insights/MemoryContextPanel', async () => ({
  default: (await hoisted.loadStubs()).marker('context-panel'),
}));
vi.mock('@/components/features/memory/replay/ConversationRecallPanel', async () => ({
  default: (await hoisted.loadStubs()).marker('recall-panel'),
}));
vi.mock('@/components/features/memory/cards/MemoryScopeHierarchyCard', async () => ({
  default: (await hoisted.loadStubs()).marker('scope-hierarchy'),
}));
vi.mock('@/components/features/settings/sections/knowledge/WorkingStateCard', async () => ({
  default: (await hoisted.loadStubs()).marker('working-state'),
}));

export const world = hoisted.world;
export const storeActions = hoisted.actions;
/** Changes the memory store the way a real update would, inside `act`. */
export const patchStore = (partial: Partial<MemoryStoreState>) => act(() => hoisted.patch(partial));
export const service = hoisted.service;
export const archive = hoisted.archive;
export const toast: Mock = hoisted.toast;
export const actionToastInfo: Mock = hoisted.actionToastInfo;

export interface ToastArgs {
  title: string;
  description?: string;
  variant?: string;
  action?: { label: string; onClick: () => Promise<void> };
}
/** Every `toast({...})` the section raised so far, oldest first. */
export const toastArgs = (): ToastArgs[] => toast.mock.calls.map(([args]) => args);

export interface ActionToastOptions {
  description: string;
  duration: number;
  action: { label: string; onClick: () => void };
}
/** Every `toast.info(title, options)` (the toast variant that carries an action link) so far, oldest first. */
export const actionToastCalls = (): [string, ActionToastOptions][] =>
  actionToastInfo.mock.calls.map(([title, options]) => [title, options]);
export const routerPush: Mock = hoisted.push;
export const setInputMessage: Mock = hoisted.setInputMessage;

/** What the section downloaded: the blobs handed to `URL.createObjectURL` and the file names of the anchor clicks. */
export const downloads: { names: string[]; blobs: Blob[] } = { names: [], blobs: [] };

const CONFIG_SETTERS = [
  'setEnableMemory',
  'setMemoryRequireConfirmation',
  'setEnableMemoryAutoExtraction',
  'setMemoryEnableConversationSearch',
  'setPreCompactEnabled',
  'setPreCompactBudgetTokens',
];

/** Fresh fixtures: logged-in user, memory enabled with vector search applied, empty store, every request succeeds. */
export function resetKit(): void {
  vi.clearAllMocks();
  hoisted.reset();
  world.auth = { user: { id: 'user-1' }, isInitialized: true };
  world.config = {
    enableMemory: true,
    memoryRequireConfirmation: false,
    enableMemoryAutoExtraction: true,
    memoryEnableConversationSearch: false,
    preCompactEnabled: false,
    preCompactBudgetTokens: 4000,
    ...Object.fromEntries(CONFIG_SETTERS.map((name) => [name, vi.fn()])),
  };
  world.retrieval = { embeddingApplied: true, checkOrphanCollections: vi.fn() };
  world.labsEnabled = false;
  world.search = new URLSearchParams();
  service.exportMemories.mockResolvedValue({ version: 1, data: { semantic: [{ id: 'm1' }] }, total_count: 2 });
  service.exportMemoriesMarkdown.mockResolvedValue(undefined);
  service.updateMemory.mockResolvedValue(undefined);
  service.updateMemoryStatus.mockResolvedValue(undefined);
  service.restoreMemory.mockResolvedValue(undefined);
  service.getMemoryTags.mockResolvedValue({ tags: [] });
  archive.dryRunImportMemories.mockResolvedValue(dryRunOf());
  archive.confirmImportMemories.mockResolvedValue(confirmOf());

  downloads.names = [];
  downloads.blobs = [];
  URL.createObjectURL = vi.fn((blob: Blob) => {
    downloads.blobs.push(blob);
    return 'blob:memories';
  });
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    downloads.names.push(this.download);
  });
}

export const renderSection = (Section: ComponentType = MemorySection): RenderResult => render(<Section />);

export const click = async (element: Element) => {
  fireEvent.click(element);
  await settle();
};

export const typeInto = async (element: Element, value: string) => {
  fireEvent.change(element, { target: { value } });
  await settle();
};

export const button = (name: string): HTMLElement => screen.getByRole('button', { name });
export const byTitle = (title: string): HTMLElement => screen.getByTitle(title);
export const byTestId = (id: string): HTMLElement => screen.getByTestId(id);
export const queryTestId = (id: string): HTMLElement | null => screen.queryByTestId(id);

/** Attribute of a stub, e.g. `attr('tab-switcher', 'data-active')`. */
export const attr = (testId: string, name: string): string | null => byTestId(testId).getAttribute(name);

/** Opens a tab through the (stubbed) tab switcher. */
export const openTab = (tab: string) => click(button(`tab:${tab}`));

/**
 * Picks a file in the toolbar's hidden import input and resolves once the section has processed it.
 * Resolves with the spy on the input's `value` setter: the section clears the input so the same file can be chosen again.
 */
export async function pickImportFile(container: HTMLElement, file: File): Promise<Mock> {
  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) {
    throw new Error('import input is not rendered');
  }
  const valueSetter = vi.fn();
  Object.defineProperty(input, 'value', { configurable: true, get: () => '', set: valueSetter });
  fireEvent.change(input, { target: { files: [file] } });
  await settle();
  return valueSetter;
}
