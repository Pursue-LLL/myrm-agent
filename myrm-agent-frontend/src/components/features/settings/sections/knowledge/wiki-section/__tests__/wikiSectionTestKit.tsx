import { act, fireEvent, screen } from '@testing-library/react';
import { vi, type Mock } from 'vitest';

import { ApiError } from '@/lib/api';
import type { WikiMaintainProgress } from '@/services/wiki/maintain';
import { settle } from '@/test-utils/fakeClock';
import type { WikiIngestSnapshot } from '../../useWikiIngestSubscription';
import type { WikiMaintainOutcome } from '../../useWikiMaintainRun';
import { healthOf, importResultOf, obsidianResultOf, queryResponseOf, statsOf } from './wikiSectionFixtures';
import { resetStubs } from './wikiSectionStubs';

/**
 * Wiki 面板测试共用工具：模块 mock（须在被测模块之前 import 本文件才会生效）、可变夹具状态、渲染与交互 helper。
 * 路由 / 提示 / 接口 / 实时队列 / 维护任务 / 子面板全部在此替换，测试只断言模块的可见行为与对外部的调用。
 */

interface MaintainRunState {
  isRunning: boolean;
  progress: WikiMaintainProgress | null;
  canCancel: boolean;
  isCancelling: boolean;
}

const hoisted = vi.hoisted(() => {
  const url = { search: new URLSearchParams(''), listeners: new Set<() => void>() };
  const setSearch = (query: string) => {
    url.search = new URLSearchParams(query);
    url.listeners.forEach((listener) => listener());
  };
  const router = {
    // 与真实路由一致: 替换后 useSearchParams 立刻给出新的查询串。
    replace: vi.fn((target: string) => setSearch(target.includes('?') ? target.slice(target.indexOf('?') + 1) : '')),
    push: vi.fn(),
  };
  const ingest = {
    snapshot: null as WikiIngestSnapshot | null,
    listeners: new Set<(snapshot: WikiIngestSnapshot) => void>(),
  };
  const maintainRun = {
    onFinished: null as null | ((outcome: WikiMaintainOutcome) => unknown),
    scope: undefined as string | null | undefined,
    state: { isRunning: false, progress: null, canCancel: false, isCancelling: false } as MaintainRunState,
    listeners: new Set<() => void>(),
    start: vi.fn(),
    cancel: vi.fn(),
  };
  return {
    url,
    setSearch,
    router,
    ingest,
    maintainRun,
    world: { locale: 'en', tauri: false },
    // Interpolation values are kept in the output so tests can assert them.
    translate: Object.assign(
      (key: string, values?: Record<string, unknown>) => (values ? `${key}|${JSON.stringify(values)}` : key),
      { has: () => true },
    ),
    toast: Object.assign(vi.fn(), {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
      info: vi.fn(),
      message: vi.fn(),
    }),
    apiRequest: vi.fn(),
    service: {
      queryWiki: vi.fn(),
      compileWiki: vi.fn(),
      resumeCompileCircuit: vi.fn(),
      getHealthReport: vi.fn(),
      getRawTree: vi.fn(),
      getQueueStatus: vi.fn(),
      repairPageTypes: vi.fn(),
      repairPublication: vi.fn(),
      reindexVectors: vi.fn(),
      importFolder: vi.fn(),
      importZip: vi.fn(),
      importObsidianFolder: vi.fn(),
      importObsidianZip: vi.fn(),
    },
    listAgents: vi.fn(),
    dialogOpen: vi.fn(),
    consumeHandoff: vi.fn(),
    metrics: { attempt: vi.fn(), submitted: vi.fn(), surface: vi.fn() },
    loadStubs: () => import('./wikiSectionStubs'),
  };
});

vi.mock('next-intl', () => ({ useTranslations: () => hoisted.translate, useLocale: () => hoisted.world.locale }));
vi.mock('next/navigation', async () => {
  const { useSyncExternalStore } = await import('react');
  return {
    useSearchParams: () =>
      useSyncExternalStore(
        (listener) => {
          hoisted.url.listeners.add(listener);
          return () => hoisted.url.listeners.delete(listener);
        },
        () => hoisted.url.search,
      ),
    useRouter: () => hoisted.router,
    usePathname: () => '/settings/wiki',
  };
});
vi.mock('sonner', () => ({ toast: hoisted.toast }));
vi.mock('@/lib/api', () => ({
  apiRequest: hoisted.apiRequest,
  getApiUrl: (path: string) => `http://api.test${path}`,
  ApiError: class ApiError extends Error {
    constructor(
      message: string,
      public code: number = 50001,
    ) {
      super(message);
    }
  },
}));
vi.mock('@/services/wikiService', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/wikiService')>()),
  wikiService: hoisted.service,
}));
vi.mock('@/services/agent', () => ({ listAgents: hoisted.listAgents }));
vi.mock('@/components/agent/builtin-agent-i18n', () => ({
  getBuiltinAgentName: (id: string, name: string, locale: string) => `${id}:${name}:${locale}`,
}));
vi.mock('@/lib/utils/clipboardUtils', () => ({ isTauri: () => hoisted.world.tauri }));
vi.mock('@tauri-apps/plugin-dialog', () => ({ open: hoisted.dialogOpen }));
vi.mock('@/lib/migrationChatHandoff', () => ({ consumeMigrationObsidianVaultImport: hoisted.consumeHandoff }));
vi.mock('@/services/wiki/evidenceMetrics', () => ({
  recordWikiQueryAttempt: hoisted.metrics.attempt,
  recordWikiQuerySubmitted: hoisted.metrics.submitted,
  recordEvidenceSurface: hoisted.metrics.surface,
}));
vi.mock('../../useWikiIngestSubscription', async () => {
  const { useEffect, useRef, useState } = await import('react');
  return {
    useWikiIngestSubscription: (_scope: unknown, options?: { onSnapshot?: (snapshot: WikiIngestSnapshot) => void }) => {
      const [snapshot, setSnapshot] = useState(hoisted.ingest.snapshot);
      const onSnapshot = useRef(options?.onSnapshot);
      onSnapshot.current = options?.onSnapshot;
      useEffect(() => {
        const listener = (next: WikiIngestSnapshot) => {
          setSnapshot(next);
          onSnapshot.current?.(next);
        };
        hoisted.ingest.listeners.add(listener);
        return () => {
          hoisted.ingest.listeners.delete(listener);
        };
      }, []);
      return { connected: snapshot !== null, snapshot };
    },
  };
});
vi.mock('../../useWikiMaintainRun', async () => {
  const { useSyncExternalStore } = await import('react');
  return {
    useWikiMaintainRun: (options: {
      agentScopeId?: string | null;
      onFinished: (outcome: WikiMaintainOutcome) => unknown;
    }) => {
      hoisted.maintainRun.onFinished = options.onFinished;
      hoisted.maintainRun.scope = options.agentScopeId;
      const state = useSyncExternalStore(
        (listener) => {
          hoisted.maintainRun.listeners.add(listener);
          return () => hoisted.maintainRun.listeners.delete(listener);
        },
        () => hoisted.maintainRun.state,
      );
      return { ...state, start: hoisted.maintainRun.start, cancel: hoisted.maintainRun.cancel };
    },
  };
});
vi.mock('@/components/primitives/select', async () => (await hoisted.loadStubs()).selectModule);
vi.mock('@/components/primitives/tabs', async () => (await hoisted.loadStubs()).tabsModule);
vi.mock('@/components/features/message-box/SourceChunkDrawer', async () =>
  (await hoisted.loadStubs()).defaultModule('SourceChunkDrawer'),
);
vi.mock('../../WikiConceptsList', async () =>
  (await hoisted.loadStubs()).namedModule('WikiConceptsList', 'WikiConceptsList'),
);
vi.mock('../../WikiPendingEdits', async () =>
  (await hoisted.loadStubs()).namedModule('WikiPendingEdits', 'WikiPendingEdits'),
);
vi.mock('../../WikiDuplicateReviewPanel', async () =>
  (await hoisted.loadStubs()).namedModule('WikiDuplicateReviewPanel', 'WikiDuplicateReviewPanel'),
);
vi.mock('../../WikiQueuePanel', async () =>
  (await hoisted.loadStubs()).namedModule('WikiQueuePanel', 'WikiQueuePanel'),
);
vi.mock('../../WikiIgnorePanel', async () =>
  (await hoisted.loadStubs()).namedModule('WikiIgnorePanel', 'WikiIgnorePanel'),
);
vi.mock('../../WikiHealthIssuesSection', async () =>
  (await hoisted.loadStubs()).namedModule('WikiHealthIssuesSection', 'WikiHealthIssuesSection'),
);
vi.mock('../../WikiCompilePhaseBar', async () =>
  (await hoisted.loadStubs()).namedModule('WikiCompilePhaseBar', 'WikiCompilePhaseBar'),
);
vi.mock('../../ima/ImaSourceCard', async () => (await hoisted.loadStubs()).defaultModule('ImaSourceCard'));
vi.mock('../../WikiSourceSyncPanel', async () => (await hoisted.loadStubs()).defaultModule('WikiSourceSyncPanel'));
vi.mock('../../SecondBrainSetupCard', async () => (await hoisted.loadStubs()).defaultModule('SecondBrainSetupCard'));
vi.mock('../../ObsidianVaultActions', async () =>
  (await hoisted.loadStubs()).namedModule('ObsidianVaultActions', 'ObsidianVaultActions'),
);
vi.mock('../../MeetingNotesImportCard', async () =>
  (await hoisted.loadStubs()).defaultModule('MeetingNotesImportCard'),
);
vi.mock('../../DailyReviewCard', async () => (await hoisted.loadStubs()).defaultModule('DailyReviewCard'));
vi.mock('../../wiki/WikiLayersLedgerPanel', async () =>
  (await hoisted.loadStubs()).namedModule('WikiLayersLedgerPanel', 'WikiLayersLedgerPanel'),
);
vi.mock('../../wiki/WikiImportConflictDialog', async () =>
  (await hoisted.loadStubs()).namedModule('WikiImportConflictDialog', 'WikiImportConflictDialog'),
);
vi.mock('../../wiki/WikiImportSecurityDialog', async () =>
  (await hoisted.loadStubs()).namedModule('WikiImportSecurityDialog', 'WikiImportSecurityDialog'),
);
vi.mock('../../wiki/WikiUrlImportDialog', async () =>
  (await hoisted.loadStubs()).namedModule('WikiUrlImportDialog', 'WikiUrlImportDialog'),
);
vi.mock('../../wiki/WikiVideoImportDialog', async () =>
  (await hoisted.loadStubs()).namedModule('WikiVideoImportDialog', 'WikiVideoImportDialog'),
);
vi.mock('../../wiki/WikiRawSourceTree', async () =>
  (await hoisted.loadStubs()).namedModule('WikiRawSourceTree', 'WikiRawSourceTree'),
);

/** 取自被 mock 的 `@/lib/api`，页面与测试共用同一个错误类。 */
export const MockedApiError = ApiError;
export const toast = hoisted.toast;
export const router = hoisted.router;
export const service = hoisted.service;
export const apiRequest: Mock = hoisted.apiRequest;
export const listAgents: Mock = hoisted.listAgents;
export const dialogOpen: Mock = hoisted.dialogOpen;
export const consumeHandoff: Mock = hoisted.consumeHandoff;
export const metrics = hoisted.metrics;
export const maintainRun = hoisted.maintainRun;
export const world = hoisted.world;

/** Every toast of one kind, as the list of its first arguments (oldest first). */
export const toastTexts = (kind: 'success' | 'error' | 'warning' | 'message'): unknown[] =>
  toast[kind].mock.calls.map(([text]) => text);

/** The URL query the page currently sits on, as the router last wrote it. */
export const currentQuery = (): string => hoisted.url.search.toString();
export const setQuery = (query: string): void => act(() => hoisted.setSearch(query));

export const patchMaintainRun = (partial: Partial<MaintainRunState>): void =>
  act(() => {
    hoisted.maintainRun.state = { ...hoisted.maintainRun.state, ...partial };
    hoisted.maintainRun.listeners.forEach((listener) => listener());
  });

/** Ends the maintenance run the way the run follower does and lets the page react. */
export const finishMaintainRun = async (outcome: WikiMaintainOutcome) => {
  await act(async () => {
    await hoisted.maintainRun.onFinished?.(outcome);
  });
  await settle();
};

/** Pushes one live ingest snapshot into every subscriber, like a server-sent event. */
export const emitIngest = async (snapshot: WikiIngestSnapshot) => {
  await act(async () => {
    hoisted.ingest.listeners.forEach((listener) => listener(snapshot));
  });
  await settle();
};

/** Fresh fixtures: default scope, tabs at the overview, every request succeeds with plain data. */
export function resetKit(): void {
  vi.clearAllMocks();
  resetStubs();
  hoisted.url.search = new URLSearchParams('');
  hoisted.ingest.snapshot = null;
  hoisted.ingest.listeners.clear();
  hoisted.maintainRun.state = { isRunning: false, progress: null, canCancel: false, isCancelling: false };
  hoisted.maintainRun.onFinished = null;
  hoisted.maintainRun.scope = undefined;
  hoisted.world.locale = 'en';
  hoisted.world.tauri = false;
  window.location.hash = '';
  apiRequest.mockImplementation(async (path: string, init?: RequestInit) => {
    if (path.includes('/wiki/purpose')) {
      return init ? {} : { purpose: 'saved purpose' };
    }
    return statsOf();
  });
  listAgents.mockResolvedValue({ items: [] });
  service.getHealthReport.mockResolvedValue(healthOf());
  service.getRawTree.mockResolvedValue([]);
  service.getQueueStatus.mockResolvedValue({ stats: {}, pending_items: [], failed_items: [], compile_run: null });
  service.queryWiki.mockResolvedValue(queryResponseOf());
  service.compileWiki.mockResolvedValue({ pending: 3, compile_run: null });
  service.resumeCompileCircuit.mockResolvedValue(undefined);
  service.repairPageTypes.mockResolvedValue({ success: true, files_repaired: 2, message: 'repaired' });
  service.repairPublication.mockResolvedValue({
    success: true,
    files_scanned: 5,
    files_repaired: 2,
    files_skipped: 0,
    reindexed: 1,
    message: 'repaired',
  });
  service.reindexVectors.mockResolvedValue({
    success: true,
    scanned: 6,
    reindexed: 6,
    concepts_reindexed: 1,
    sidecars_reindexed: 2,
    assets_indexed: 3,
    skipped_drafts: 0,
    failed: 0,
    errors: [],
    message: 'reindexed',
  });
  service.importFolder.mockResolvedValue(importResultOf());
  service.importZip.mockResolvedValue(importResultOf());
  service.importObsidianFolder.mockResolvedValue(obsidianResultOf());
  service.importObsidianZip.mockResolvedValue(obsidianResultOf());
  dialogOpen.mockResolvedValue('/picked/folder');
  consumeHandoff.mockReturnValue(null);
  hoisted.maintainRun.cancel.mockResolvedValue(undefined);
}

export const click = async (element: Element) => {
  fireEvent.click(element);
  await settle();
};

export const typeInto = async (element: Element, value: string) => {
  fireEvent.change(element, { target: { value } });
  await settle();
};

export const button = (name: string): HTMLElement => screen.getByRole('button', { name });
export const queryButton = (name: string): HTMLElement | null => screen.queryByRole('button', { name });
export const byTestId = (id: string): HTMLElement => screen.getByTestId(id);
export const queryTestId = (id: string): HTMLElement | null => screen.queryByTestId(id);

/** Chooses an option of a (stubbed) select the way a user would: by clicking it. */
export const choose = (optionName: string) => click(screen.getByRole('option', { name: optionName }));
