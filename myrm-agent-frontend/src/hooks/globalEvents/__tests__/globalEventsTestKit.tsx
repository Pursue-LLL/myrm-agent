/**
 * Test kit for useGlobalEvents: stubs the SSE / BroadcastChannel transports and every collaborator the
 * event handlers reach, so a test can push one server event and observe every side effect it causes.
 */
import { afterEach, beforeEach, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';

const hoisted = vi.hoisted(() => ({
  router: { push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() },
  toast: { info: vi.fn(), success: vi.fn(), warning: vi.fn(), error: vi.fn(), dismiss: vi.fn() },
  notify: vi.fn(),
  config: { enableWebNotifications: true },
  agentState: { selectedAgent: null as { id: string } | null },
  fetchAgents: vi.fn(),
  fetchAgent: vi.fn(),
  syncBoundChatAgentConfig: vi.fn(),
  fetchLocalSkills: vi.fn(),
  fetchUserSkillConfig: vi.fn(),
  openApproval: vi.fn(),
  closeApproval: vi.fn(),
  refreshActiveGoal: vi.fn(),
  fetchQueue: vi.fn(),
  markStale: vi.fn(),
  showBudgetExceeded: vi.fn(),
  mutateSwr: vi.fn(),
  refreshOpenChatTranscript: vi.fn(),
  chat: { chatId: '' },
  shellJobFinish: vi.fn(),
  voiceJobFinish: vi.fn(),
  showMessageDeadLetteredToast: vi.fn(),
  showMemoryOperationToasts: vi.fn(),
  showLocatorHealedToast: vi.fn(),
  showKanbanTaskToast: vi.fn(),
  showSkillLearnedToast: vi.fn(),
  showSkillEvolvedToast: vi.fn(),
  showSubsumptionUndoToast: vi.fn(),
  showMcpAuthRequiredToast: vi.fn(),
  showOAuthReauthRequiredToast: vi.fn(),
  showBackupFailureToast: vi.fn(),
  showCloudSyncFailureToast: vi.fn(),
}));

export const mocks = hoisted;

vi.mock('next/navigation', () => ({ useRouter: () => hoisted.router }));
vi.mock('swr', () => ({ mutate: hoisted.mutateSwr }));
vi.mock('@/lib/utils/toast', () => ({ toast: hoisted.toast }));
vi.mock('@/lib/deploy-mode', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/deploy-mode')>()),
  getNotificationStreamUrl: () => 'http://test.local/notifications/stream',
}));
vi.mock('@/services/notification', () => ({ notificationService: { notify: hoisted.notify } }));
vi.mock('@/store/useConfigStore', () => ({
  default: (select: (state: typeof hoisted.config) => unknown) => select(hoisted.config),
}));
vi.mock('@/store/useApprovalStore', () => ({
  normalizeApprovalPayload: (data: Record<string, unknown>) => ({ ...data, normalized: true }),
  default: { getState: () => ({ openApproval: hoisted.openApproval, closeApproval: hoisted.closeApproval }) },
}));
vi.mock('@/store/useBudgetExceededStore', () => ({
  useBudgetExceededStore: { getState: () => ({ show: hoisted.showBudgetExceeded }) },
}));
vi.mock('@/store/useAgentStore', () => ({
  default: {
    getState: () => ({
      selectedAgent: hoisted.agentState.selectedAgent,
      fetchAgents: hoisted.fetchAgents,
      fetchAgent: hoisted.fetchAgent,
    }),
  },
}));
vi.mock('@/store/skill/useSkillStore', () => ({
  default: {
    getState: () => ({
      fetchLocalSkills: hoisted.fetchLocalSkills,
      fetchUserSkillConfig: hoisted.fetchUserSkillConfig,
    }),
  },
}));
vi.mock('@/store/chat/goals/useGoalStore', () => ({
  useGoalStore: {
    getState: () => ({ refreshActiveGoal: hoisted.refreshActiveGoal, fetchQueue: hoisted.fetchQueue }),
  },
}));
vi.mock('@/store/chat/useSubagentStore', () => ({
  useSubagentStore: { getState: () => ({ markStale: hoisted.markStale }) },
}));
vi.mock('@/store/useChatStore', () => ({ default: { getState: () => hoisted.chat } }));
vi.mock('@/store/chat/chatTranscriptRefresh', () => ({ refreshOpenChatTranscript: hoisted.refreshOpenChatTranscript }));
vi.mock('@/services/backgroundTasksRefresh', () => ({
  notifyBackgroundTasksChangedForShellJobFinish: hoisted.shellJobFinish,
  notifyBackgroundTasksChangedForVoiceJobFinish: hoisted.voiceJobFinish,
}));
vi.mock('@/hooks/globalEvents/syncBoundChatAgentConfig', () => ({
  syncBoundChatAgentConfig: hoisted.syncBoundChatAgentConfig,
}));
vi.mock('@/hooks/globalEvents/messageDeadLetteredToast', () => ({
  showMessageDeadLetteredToast: hoisted.showMessageDeadLetteredToast,
}));
vi.mock('@/hooks/globalEvents/memoryOperationToasts', () => ({
  showMemoryOperationToasts: hoisted.showMemoryOperationToasts,
}));
vi.mock('@/hooks/globalEvents/locatorHealedToast', () => ({ showLocatorHealedToast: hoisted.showLocatorHealedToast }));
vi.mock('@/hooks/globalEvents/kanbanTaskToast', () => ({ showKanbanTaskToast: hoisted.showKanbanTaskToast }));
vi.mock('@/hooks/globalEvents/skillGrowthToasts', () => ({
  showSkillLearnedToast: hoisted.showSkillLearnedToast,
  showSkillEvolvedToast: hoisted.showSkillEvolvedToast,
}));
vi.mock('@/hooks/globalEvents/subsumptionUndoToast', () => ({
  showSubsumptionUndoToast: hoisted.showSubsumptionUndoToast,
}));
vi.mock('@/hooks/globalEvents/reauthToasts', () => ({
  showMcpAuthRequiredToast: hoisted.showMcpAuthRequiredToast,
  showOAuthReauthRequiredToast: hoisted.showOAuthReauthRequiredToast,
}));
vi.mock('@/hooks/globalEvents/backupAlertToast', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/hooks/globalEvents/backupAlertToast')>()),
  showBackupFailureToast: hoisted.showBackupFailureToast,
  showCloudSyncFailureToast: hoisted.showCloudSyncFailureToast,
}));

import { useGlobalEvents } from '../useGlobalEvents';

export class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onopen: (() => void | Promise<void>) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn();
  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }
}

export class FakeBroadcastChannel {
  static instances: FakeBroadcastChannel[] = [];
  onmessage: ((event: MessageEvent<{ kind: string; payload?: unknown; tabId?: string }>) => void) | null = null;
  postMessage = vi.fn();
  close = vi.fn();
  constructor(readonly name: string) {
    FakeBroadcastChannel.instances.push(this);
  }
}

export const LEADER_KEY = 'myrm-sse-leader';

/** Clears every recorded call and restores the defaults the tests rely on. */
export function resetGlobalEventsKit(): void {
  vi.clearAllMocks();
  FakeEventSource.instances = [];
  FakeBroadcastChannel.instances = [];
  localStorage.clear();
  hoisted.config.enableWebNotifications = true;
  hoisted.agentState.selectedAgent = null;
  hoisted.chat.chatId = '';
  hoisted.syncBoundChatAgentConfig.mockResolvedValue(undefined);
  vi.stubGlobal('EventSource', FakeEventSource);
  vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel);
}

/** Mounts the hook; with no leader recorded in localStorage this tab becomes the leader and opens the stream. */
export function mountGlobalEvents() {
  const view = renderHook(() => useGlobalEvents());
  return { ...view, source: FakeEventSource.instances[FakeEventSource.instances.length - 1] };
}

/** Delivers one server-sent event to the leader tab's stream. */
export function emit(type: string, data: Record<string, unknown> = {}): void {
  const source = FakeEventSource.instances[FakeEventSource.instances.length - 1];
  act(() => {
    source.onmessage?.({
      data: JSON.stringify({ type, data, timestamp: '2026-01-01T00:00:00Z' }),
    } as MessageEvent<string>);
  });
}

/** Records the window events dispatched while a test runs. */
export function recordWindowEvents(): () => Array<{ type: string; detail: unknown }> {
  const spy = vi.spyOn(window, 'dispatchEvent');
  return () => spy.mock.calls.map(([event]) => ({ type: event.type, detail: (event as CustomEvent).detail }));
}

export interface ToastOptions {
  id?: string;
  description?: string;
  duration?: number;
  dismissible?: boolean;
  action?: { label: string; onClick: () => void };
}

type ToastSpy = { mock: { calls: unknown[][] } };

/** The options argument of the n-th call of a toast spy. */
export function toastOptions(toast: ToastSpy, call = 0): ToastOptions {
  return toast.mock.calls[call][1] as ToastOptions;
}

/** The message argument of the n-th call of a toast spy. */
export function toastMessage(toast: ToastSpy, call = 0): unknown {
  return toast.mock.calls[call][0];
}

/** Registers the per-test reset and fake timers every useGlobalEvents suite relies on. */
export function installGlobalEventsLifecycle(): void {
  beforeEach(() => {
    resetGlobalEventsKit();
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });
}
