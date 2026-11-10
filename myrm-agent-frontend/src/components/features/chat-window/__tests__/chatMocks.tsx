/**
 * [INPUT]
 * - vitest::vi (POS: 模块替身登记)
 * - @/store/useChatStore (POS: 被测组件读写的真实 store)
 *
 * [OUTPUT]
 * - probes: 替身的可观测句柄（查询参数、滚动镜像、虚拟列表、各回调）
 * - openChat / makeMessages: 往 store 放会话与消息
 * - setUpChatTest / tearDownChatTest: 每个用例的假定时器、浏览器替身与默认状态
 * - installBrowserStubs / scrollWindowTo: jsdom 缺失的滚动相关 API 与 window 滚动
 * - 副作用：把 Chat 的子组件替换为探针（把收到的属性写进 DOM、暴露回调按钮）或空组件
 *
 * [POS]
 * Chat 行为测试的共享底座。必须先于 ../Chat 导入：vi.mock 在本模块求值时登记，之后加载的 Chat 才拿到这些替身。
 */
import { cleanup } from '@testing-library/react';
import { useEffect, useRef, type MutableRefObject, type ReactNode } from 'react';
import { vi } from 'vitest';
import type { ScrollFollowMirrorEntry } from '@/hooks/ui/useScrollPositionRestore';
import type { ChatState, Message } from '@/store/chat/types';
import { useRewindStore } from '@/store/chat/useRewindStore';
import useChatStore from '@/store/useChatStore';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import { useUserQuestionNavStore } from '../question-nav';

interface ConfigErrorProbe {
  error_type: string;
}

const probes = vi.hoisted(() => ({
  searchParams: new URLSearchParams(),
  nearBottom: { value: false },
  configError: { value: null as ConfigErrorProbe | null },
  clearConfigError: vi.fn(),
  fastFocus: vi.fn(),
  scroll: {
    save: vi.fn(),
    restore: vi.fn(() => true),
    snapshot: vi.fn((): ScrollFollowMirrorEntry | null => null),
    onRestore: null as ((entry: ScrollFollowMirrorEntry) => void) | null,
    userScrolled: null as MutableRefObject<boolean> | null,
    followingBottom: null as MutableRefObject<boolean> | null,
    saveTimer: null as MutableRefObject<ReturnType<typeof setTimeout> | null> | null,
  },
  virtual: {
    scrollToIndex: vi.fn(),
    scrollToBottom: vi.fn(),
    lastProps: null as { messageCount: number; highlightMessageId: string | null | undefined } | null,
  },
  messageInputMounts: [] as string[],
}));
export { probes };

const realSyncMessages = useUserQuestionNavStore.getState().syncMessages;
const realLoadThroughTurn = useChatStore.getState().loadThroughTurn;

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('next/navigation', () => ({ useSearchParams: () => probes.searchParams }));
vi.mock('@/lib/utils/domUtils', () => ({ isNearBottom: () => probes.nearBottom.value }));
vi.mock('@/hooks/settings/useConfigErrorDetector', () => ({
  useConfigErrorDetector: () => ({
    configError: probes.configError.value,
    clearConfigError: probes.clearConfigError,
  }),
}));
vi.mock('../useComposerFastFocus', () => ({ useComposerFastFocus: probes.fastFocus }));
vi.mock('@/hooks/ui/useScrollPositionRestore', () => ({
  useScrollPositionRestore: (options: { onRestore?: (entry: ScrollFollowMirrorEntry) => void }) => {
    const userScrolledRef = useRef(false);
    const isFollowingBottomRef = useRef(true);
    const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    probes.scroll.onRestore = options.onRestore ?? null;
    probes.scroll.userScrolled = userScrolledRef;
    probes.scroll.followingBottom = isFollowingBottomRef;
    probes.scroll.saveTimer = saveTimerRef;
    return {
      saveScrollPosition: probes.scroll.save,
      restoreScrollPosition: probes.scroll.restore,
      getScrollMirrorSnapshot: probes.scroll.snapshot,
      userScrolledRef,
      isFollowingBottomRef,
      saveTimerRef,
    };
  },
}));

vi.mock('../MessageInput', () => {
  function MessageInputProbe({ loading }: { loading: boolean }) {
    useEffect(() => {
      probes.messageInputMounts.push(useChatStore.getState().chatId ?? '');
    }, []);
    return <div data-testid="message-input" data-loading={String(loading)} />;
  }
  return { default: MessageInputProbe };
});
vi.mock('../../companion/CompanionWidget', () => ({ default: () => null }));
vi.mock('../agent-config-panel/AgentConfigPanel', () => ({ default: () => <div data-testid="agent-config-panel" /> }));
vi.mock('../approval/VisualApprovalOsOverlaySync', () => ({ default: () => null }));
vi.mock('../ComposerClearanceSpacer', () => ({
  ComposerClearanceSpacer: () => <div data-testid="clearance-spacer" />,
}));
vi.mock('../CompactedSummaryView', () => ({ CompactedSummaryView: () => <div data-testid="compacted-summary" /> }));
vi.mock('../goals/GoalControlPlane', () => ({ GoalControlPlane: () => <div data-testid="goal-control-plane" /> }));

vi.mock('../../message-box/MessageBox', () => ({
  default: ({
    message,
    messageIndex,
    loading,
    isLast,
  }: {
    message: Message;
    messageIndex: number;
    loading: boolean;
    isLast: boolean;
  }) => (
    <div
      data-testid="message-box"
      data-message={message.messageId}
      data-index={messageIndex}
      data-loading={String(loading)}
      data-last={String(isLast)}
    />
  ),
}));
vi.mock('../../message-box/MessageBoxLoading', () => ({ default: () => <div data-testid="message-loading" /> }));

vi.mock('../virtual-message-list', () => ({
  VirtualMessageList: (props: {
    messages: Message[];
    highlightMessageId: string | null | undefined;
    scrollToMessageRef: MutableRefObject<((index: number) => void) | null>;
    scrollToBottomRef: MutableRefObject<(() => void) | null>;
    onUserScrolledChange: (scrolledUp: boolean) => void;
  }) => {
    const { scrollToMessageRef, scrollToBottomRef } = props;
    useEffect(() => {
      scrollToMessageRef.current = probes.virtual.scrollToIndex;
      scrollToBottomRef.current = probes.virtual.scrollToBottom;
    }, [scrollToMessageRef, scrollToBottomRef]);
    probes.virtual.lastProps = { messageCount: props.messages.length, highlightMessageId: props.highlightMessageId };
    return (
      <div data-testid="virtual-list" data-count={props.messages.length}>
        <button type="button" onClick={() => props.onUserScrolledChange(true)}>
          virtual scrolled up
        </button>
        <button type="button" onClick={() => props.onUserScrolledChange(false)}>
          virtual at bottom
        </button>
      </div>
    );
  },
}));

vi.mock('../ScrollToBottomButton', () => ({
  default: (props: {
    visible: boolean;
    hasNewMessage: boolean;
    onClick: () => void;
    pendingCount?: number;
    pendingItems?: unknown[];
  }) =>
    props.visible ? (
      <button
        type="button"
        data-testid="scroll-bottom"
        data-new={String(props.hasNewMessage)}
        data-pending={props.pendingCount}
        data-items={props.pendingItems?.length}
        onClick={props.onClick}
      >
        scroll to bottom
      </button>
    ) : null,
}));

vi.mock('../TurnTimelineRail', () => ({
  TurnTimelineRail: (props: {
    messages: Message[];
    turnOutlines: unknown[];
    loading: boolean;
    hasGoalPanel?: boolean;
    onJump: (index: number) => void;
    onJumpToMessageId?: (messageId: string) => void;
    onLoadThroughTurn?: (messageId: string) => Promise<boolean>;
  }) => (
    <div
      data-testid="turn-rail"
      data-count={props.messages.length}
      data-outlines={props.turnOutlines.length}
      data-loading={String(props.loading)}
      data-goal={String(props.hasGoalPanel)}
    >
      <button type="button" onClick={() => props.onJump(1)}>
        rail jump index
      </button>
      <button type="button" onClick={() => props.onJumpToMessageId?.('m2')}>
        rail jump id
      </button>
      <button type="button" onClick={() => void props.onLoadThroughTurn?.('m3')}>
        rail load turn
      </button>
    </div>
  ),
  MobileTurnOutlineSheet: (props: {
    messages: Message[];
    trigger: ReactNode;
    onJump: (index: number) => void;
    onJumpToMessageId?: (messageId: string) => void;
    onLoadThroughTurn?: (messageId: string) => Promise<boolean>;
  }) => (
    <div data-testid="mobile-outline" data-count={props.messages.length}>
      {props.trigger}
      <button type="button" onClick={() => props.onJump(1)}>
        mobile jump index
      </button>
      <button type="button" onClick={() => props.onJumpToMessageId?.('m2')}>
        mobile jump id
      </button>
      <button type="button" onClick={() => void props.onLoadThroughTurn?.('m3')}>
        mobile load turn
      </button>
    </div>
  ),
}));

vi.mock('../approval/HumanAttentionBar', () => ({
  default: (props: { messages: Message[]; onJumpToMessage: (index: number) => void }) => (
    <button
      type="button"
      data-testid="attention-bar"
      data-count={props.messages.length}
      onClick={() => props.onJumpToMessage(1)}
    >
      attention jump
    </button>
  ),
}));

/** The navigators count questions, not messages: the index they report never points at the message they name. */
const NAV_QUESTION_INDEX = 7;

vi.mock('../question-nav', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../question-nav')>()),
  UserQuestionNav: (props: { onJumpToMessageIndex: (index: number, messageId: string) => void }) => (
    <button type="button" onClick={() => props.onJumpToMessageIndex(NAV_QUESTION_INDEX, 'm1')}>
      question nav jump
    </button>
  ),
  UserQuestionOutlineDrawer: (props: { onJumpToMessageIndex: (index: number, messageId: string) => void }) => (
    <button type="button" onClick={() => props.onJumpToMessageIndex(NAV_QUESTION_INDEX, 'm2')}>
      question drawer jump
    </button>
  ),
}));

vi.mock('@/components/error-boundary/ProviderConfigErrorDialog', () => ({
  default: (props: { error: ConfigErrorProbe | null; onClose: () => void }) => (
    <div data-testid="config-error" data-error={props.error?.error_type ?? ''}>
      <button type="button" onClick={props.onClose}>
        close config error
      </button>
    </div>
  ),
}));
vi.mock('@/components/features/settings/sections/system/SessionAnalyticsDialog', () => ({
  default: (props: { sessionId: string; onClose: () => void }) => (
    <div data-testid="analytics" data-session={props.sessionId}>
      <button type="button" onClick={props.onClose}>
        close analytics
      </button>
    </div>
  ),
}));
vi.mock('../RewindDialog', () => ({
  RewindDialog: (props: {
    open: boolean;
    chatId: string;
    messageId: string;
    messageIndex: number;
    onOpenChange: (open: boolean) => void;
  }) => (
    <div data-testid="rewind" data-chat={props.chatId} data-message={props.messageId} data-index={props.messageIndex}>
      <button type="button" onClick={() => props.onOpenChange(false)}>
        close rewind
      </button>
      <button type="button" onClick={() => props.onOpenChange(true)}>
        keep rewind
      </button>
    </div>
  ),
}));

/** Builds `count` alternating user / assistant messages `m1`…`mN` in chat `chatId`. */
export function makeMessages(count: number, chatId = 'chat-1'): Message[] {
  return Array.from({ length: count }, (_, index) => ({
    messageId: `m${index + 1}`,
    chatId,
    createdAt: new Date(2026, 0, 1, 0, index),
    content: `content ${index + 1}`,
    role: index % 2 === 0 ? ('user' as const) : ('assistant' as const),
  }));
}

/** Puts a conversation into the store. */
export function openChat(chatId: string, messages: Message[], overrides: Partial<ChatState> = {}): void {
  useChatStore.setState({
    chatId,
    messages,
    compactedSummary: null,
    turnOutlines: [],
    activeSessionAnalyticsId: null,
    ...overrides,
  });
}

export interface BrowserStubs {
  /** Elements `scrollIntoView` was called on, with the options it received. */
  scrolled: { id: string | null; options: ScrollIntoViewOptions }[];
  /** Runs every queued animation-frame callback, including ones queued while running. */
  flushFrames: () => void;
  /** Runs only the callbacks queued right now; ones they queue wait for the next call. */
  stepFrame: () => void;
  /** Tells every ResizeObserver the observed box now has this content height. */
  notifyResize: (height: number) => void;
  /** How many animation-frame callbacks are queued right now. */
  pendingFrames: () => number;
}

/** jsdom has no `scrollIntoView`, `CSS.escape` or `ResizeObserver`; animation frames run only when stepped. */
export function installBrowserStubs(): BrowserStubs {
  const scrolled: BrowserStubs['scrolled'] = [];
  Object.defineProperty(Element.prototype, 'scrollIntoView', {
    configurable: true,
    writable: true,
    value(this: Element, options: ScrollIntoViewOptions) {
      const id = this.getAttribute('data-message-id') ?? (this.hasAttribute('data-message-end') ? 'end' : null);
      scrolled.push({ id, options });
    },
  });
  vi.stubGlobal('CSS', { escape: (value: string) => value });

  let frames: FrameRequestCallback[] = [];
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => frames.push(callback));
  const stepFrame = () => {
    const due = frames;
    frames = [];
    due.forEach((callback) => callback(0));
  };
  const flushFrames = () => {
    while (frames.length > 0) {
      stepFrame();
    }
  };

  const resizeCallbacks: ResizeObserverCallback[] = [];
  vi.stubGlobal(
    'ResizeObserver',
    class {
      constructor(callback: ResizeObserverCallback) {
        resizeCallbacks.push(callback);
      }
      observe() {}
      disconnect() {}
      unobserve() {}
    },
  );
  const notifyResize = (height: number) => {
    const entries = [{ contentRect: { height } }] as unknown as ResizeObserverEntry[];
    resizeCallbacks.forEach((callback) => callback(entries, {} as unknown as ResizeObserver));
  };
  return { scrolled, flushFrames, stepFrame, notifyResize, pendingFrames: () => frames.length };
}

function setWindowScroll(top: number): void {
  Object.defineProperty(window, 'scrollY', { configurable: true, writable: true, value: top });
}

/** Moves the window scroll offset and fires the scroll event. */
export function scrollWindowTo(top: number): void {
  setWindowScroll(top);
  window.dispatchEvent(new Event('scroll'));
}

/** Fresh browser stubs, fake timers and default probe / store state for one test. */
export function setUpChatTest(): BrowserStubs {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  const browser = installBrowserStubs();
  setWindowScroll(0);
  probes.searchParams = new URLSearchParams();
  probes.nearBottom.value = false;
  probes.configError.value = null;
  probes.messageInputMounts.length = 0;
  probes.virtual.lastProps = null;
  probes.scroll.snapshot.mockReturnValue(null);
  useFeatureGateStore.setState({ enabledFeatures: new Set() });
  useRewindStore.setState({ target: null });
  useUserQuestionNavStore.setState({ pendingCount: 0, pendingItems: [], syncMessages: realSyncMessages });
  useChatStore.setState({ loadThroughTurn: realLoadThroughTurn });
  document.title = 'before';
  return browser;
}

export function tearDownChatTest(): void {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.clearAllMocks();
  document.documentElement.style.removeProperty('--message-input-width');
}
