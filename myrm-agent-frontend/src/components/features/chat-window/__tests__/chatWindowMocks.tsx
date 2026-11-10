/**
 * [INPUT]
 * - vitest::vi (POS: 模块替身登记)
 * - @/store/useChatStore, useConfigStore (POS: 被测窗口读写的真实 store)
 *
 * [OUTPUT]
 * - navigation: next/navigation 的路由方法与查询参数
 * - openChatInStore: 把某个已加载的会话放进 store
 * - 副作用：把 ChatWindow 的子组件替换为探针（把收到的属性写进 DOM）或空组件
 *
 * [POS]
 * ChatWindow 行为测试的共享底座。必须先于 ../ChatWindow 导入：vi.mock 在本模块求值时登记，之后加载的
 * ChatWindow 才拿到这些替身。
 */
import { vi } from 'vitest';
import type { ChatState } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';
import { useExtensionUIStore } from '@/store/useExtensionUIStore';

const routing = vi.hoisted(() => ({
  replace: vi.fn(),
  push: vi.fn(),
  prefetch: vi.fn(),
  searchParams: new URLSearchParams(),
}));
export const navigation = routing;

// One object for every render, as Next's router is: a fresh one per render would re-run every effect that lists it.
const stableRouter = { replace: routing.replace, push: routing.push, prefetch: routing.prefetch };

vi.mock('next/navigation', () => ({
  useRouter: () => stableRouter,
  useSearchParams: () => routing.searchParams,
  usePathname: () => '/',
}));

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({ useTranslations: () => stableT }));

vi.mock('next/error', () => ({
  default: ({ statusCode }: { statusCode: number }) => <div data-testid="next-error">{statusCode}</div>,
}));
vi.mock('@/hooks/shared/usePendingMemoryToast', () => ({ usePendingMemoryToast: () => undefined }));

vi.mock('../Chat', () => ({
  default: ({ messagesOverride }: { messagesOverride?: unknown[] }) => (
    <div data-testid="chat" data-override={messagesOverride?.length ?? 'none'} />
  ),
}));
vi.mock('../EmptyChat', () => ({ default: () => <div data-testid="empty-chat" /> }));
vi.mock('../MessageListSkeleton', () => ({ default: () => <div data-testid="skeleton" /> }));
vi.mock('../AgentInfoBanner', () => ({
  default: ({ agentId }: { agentId: string }) => <div data-testid="agent-banner">{agentId}</div>,
}));
vi.mock('../FiveContractDeliveryStatusPanel', () => ({
  FiveContractDeliveryStatusPanel: () => <div data-testid="five-contract" />,
}));
vi.mock('@/components/features/memory/pending/MemoryConflictChatBanner', () => ({
  default: () => <div data-testid="memory-conflict-banner" />,
}));
vi.mock('@/components/features/settings/sections/system/ExecutionTraceTimeline', () => ({
  default: ({ sessionId, pollMs }: { sessionId: string; pollMs?: number }) => (
    <div data-testid="trace" data-poll={String(pollMs)}>
      {sessionId}
    </div>
  ),
}));
vi.mock('@/components/features/memory/pending/PendingMemoryBadge', () => ({
  default: ({ onClick }: { onClick: () => void }) => (
    <button type="button" onClick={onClick}>
      pending memory badge
    </button>
  ),
}));
vi.mock('@/components/features/copilot/SessionAdvisorPanel', () => ({
  default: (props: {
    open: boolean;
    initialQuestion: string;
    selectionSnippet?: string;
    onOpenChange: (open: boolean) => void;
  }) => (
    <div
      data-testid="advisor"
      data-open={String(props.open)}
      data-question={props.initialQuestion}
      data-selection={props.selectionSnippet ?? ''}
    >
      <button type="button" onClick={() => props.onOpenChange(false)}>
        close advisor
      </button>
    </div>
  ),
}));
vi.mock('../ChatWindowSatellites', () => ({
  default: ({ chatId }: { chatId?: string }) => <div data-testid="satellites" data-chat={chatId ?? ''} />,
  GoalControlPlane: () => <div data-testid="goal-control-plane" />,
  GoalStatusCard: () => <div data-testid="goal-status-card" />,
  LifeStatusCapsule: () => null,
}));

vi.mock('../ToolApprovalDialog', () => ({ default: () => null }));
vi.mock('../ToolApprovalExpiryWatcher', () => ({ default: () => null }));
vi.mock('../YoloModeBanner', () => ({ default: () => null }));
vi.mock('../EStopBanner', () => ({ default: () => null }));
vi.mock('../ExtensionDisconnectedBanner', () => ({ default: () => null }));
vi.mock('../ExtensionTakeoverBanner', () => ({ default: () => null }));
vi.mock('../LoopStatusBar', () => ({ LoopStatusBar: () => null }));
vi.mock('../ParentChatLink', () => ({ ParentChatLink: () => null }));
vi.mock('../ChatCronLink', () => ({ ChatCronLink: () => null }));
vi.mock('../ReplayAction', () => ({ default: () => null }));
vi.mock('../SessionExportButton', () => ({ default: () => null }));
vi.mock('../DashboardWorkspaceLink', () => ({ DashboardWorkspaceLink: () => null }));
vi.mock('../WorkingStateBadge', () => ({ default: () => null }));
vi.mock('../artifacts/ArtifactPortal', () => ({ default: () => null }));
vi.mock('../../extension-ui', () => ({ ExtensionUIModal: () => null }));
vi.mock('../../task-hud', () => ({ TaskHudOverlay: () => null }));
vi.mock('@/components/features/project-workspace/WorkspaceTrustBanner', () => ({ default: () => null }));
vi.mock('@/components/features/message-actions/SessionRevertButton', () => ({ default: () => null }));
vi.mock('@/components/features/copilot/RunStatusChip', () => ({ default: () => null }));
vi.mock('@/components/features/memory/pending/PendingMemoryDialog', () => ({ default: () => null }));

/** Puts a loaded conversation into the store, with nothing running and the network loads of the window stubbed out. */
export function openChatInStore(chatId: string, overrides: Partial<ChatState> = {}): void {
  useChatStore.setState({
    chatId,
    messages: [],
    isMessagesLoaded: true,
    loading: false,
    messageAppeared: false,
    notFound: false,
    loadError: false,
    compactedSummary: null,
    agentConfig: null,
    ...overrides,
  });
  useConfigStore.setState({ initConfig: vi.fn().mockResolvedValue(undefined) });
  useExtensionUIStore.setState({ fetchPending: vi.fn().mockResolvedValue(undefined) });
}
