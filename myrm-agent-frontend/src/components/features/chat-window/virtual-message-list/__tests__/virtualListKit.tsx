/**
 * [INPUT]
 * - vitest::vi (POS: 模块替身登记)
 * - @/store/useChatStore (POS: 被测组件读取的真实 store)
 * - @/hooks/ui/useScrollPositionRestore (POS: 真实的滚动镜像总线，镜像写进 sessionStorage)
 *
 * [OUTPUT]
 * - kit: 虚拟化器替身的可观测句柄（可见窗口、总高度、scrollToIndex / measure 调用、收到的选项）
 * - installListStubs: 手动推进的 requestAnimationFrame、行高测量与 sessionStorage 清理
 * - settle: 让假定时器走过若干毫秒（包在 act 里）
 * - renderList: 以默认属性渲染 VirtualMessageList，返回滚动容器与 update
 * - setScrollMetrics / scrollTo: 给滚动容器设置 scrollTop、scrollHeight、clientHeight 并触发 scroll 事件
 * - readMirror / writeMirror: 读写某会话的滚动镜像
 *
 * [POS]
 * VirtualMessageList 行为测试的共享底座。必须先于 ../VirtualMessageList 导入：vi.mock 在本模块求值时登记。
 * 虚拟化器是库、不是被测对象，所以换成窗口可控的替身；滚动镜像、store 与消息行都是真实的。
 */
import { act, cleanup, fireEvent, render } from '@testing-library/react';
import type { MutableRefObject, RefObject } from 'react';
import { vi, type Mock } from 'vitest';
import type { ScrollFollowMirrorEntry } from '@/hooks/ui/useScrollPositionRestore';
import type { Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import VirtualMessageList from '../VirtualMessageList';

interface VirtualizerOptionsProbe {
  count: number;
  overscan: number;
  estimateSize: (index: number) => number;
  measureElement: (element: Element) => number;
  getScrollElement: () => HTMLElement | null;
}

const kit = vi.hoisted(() => {
  const state = { start: 0, end: 0, total: 1000, options: null as VirtualizerOptionsProbe | null };
  const virtualizer = {
    /** Called once per render of the list, so its call count is the render count. */
    getVirtualItems: vi.fn(() =>
      Array.from({ length: Math.max(0, state.end - state.start) }, (_, offset) => {
        const index = state.start + offset;
        return { index, key: `row-${index}`, start: index * 100, size: 100 };
      }),
    ),
    getTotalSize: () => state.total,
    scrollToIndex: vi.fn(),
    measure: vi.fn(),
    measureElement: vi.fn<(element: Element | null) => void>(),
  };
  return { state, virtualizer };
});
export { kit };

vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: (options: VirtualizerOptionsProbe) => {
    kit.state.options = options;
    return kit.virtualizer;
  },
}));
vi.mock('../../../message-box/MessageBox', () => ({
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
vi.mock('../../../message-box/MessageBoxLoading', () => ({ default: () => <div data-testid="message-loading" /> }));
vi.mock('../../CompactedSummaryView', () => ({ CompactedSummaryView: () => <div data-testid="compacted-summary" /> }));
vi.mock('../../ComposerClearanceSpacer', () => ({
  ComposerClearanceSpacer: ({
    columnRef,
    className,
  }: {
    columnRef: RefObject<HTMLElement | null>;
    className: string;
  }) => (
    <div
      data-testid="clearance-spacer"
      data-class={className}
      data-column={columnRef.current?.getAttribute('data-column') ?? ''}
    />
  ),
}));

const MIRROR_KEY_PREFIX = 'myrm_scroll_mirror_';
let chatCounter = 0;

/** The mirror cache outlives a test, so every test gets a conversation id nobody saved a position for. */
export function freshChatId(): string {
  chatCounter += 1;
  return `virtual-chat-${chatCounter}`;
}

export interface ListStubs {
  /** Runs every queued animation-frame callback, including ones queued while running. */
  flushFrames: () => void;
  /** Sets the height `getBoundingClientRect` reports for message rows (0 = not laid out). */
  setRowHeight: (height: number) => void;
}

/** Animation frames run only when stepped; rows report the height set with `setRowHeight`. */
export function installListStubs(): ListStubs {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  let frames: FrameRequestCallback[] = [];
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => frames.push(callback));
  let rowHeight = 0;
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    return { height: this.hasAttribute('data-message-id') ? rowHeight : 0 } as DOMRect;
  });
  sessionStorage.clear();
  kit.state.start = 0;
  kit.state.end = 0;
  kit.state.total = 1000;
  kit.state.options = null;
  useChatStore.setState({
    hasMoreMessages: false,
    loadingOlder: false,
    loadOlderMessages: vi.fn(() => Promise.resolve()),
  });
  return {
    flushFrames: () => {
      while (frames.length > 0) {
        const due = frames;
        frames = [];
        due.forEach((callback) => callback(0));
      }
    },
    setRowHeight: (height) => {
      rowHeight = height;
    },
  };
}

/** Lets `ms` of fake time pass inside act, so timers fire and their state updates are flushed. */
export const settle = (ms: number): void => act(() => void vi.advanceTimersByTime(ms));

export function tearDownList(): void {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.clearAllMocks();
}

/** Builds `count` alternating user / assistant messages `m1`…`mN`. */
export function makeMessages(count: number, chatId = 'chat-1'): Message[] {
  return Array.from({ length: count }, (_, index) => ({
    messageId: `m${index + 1}`,
    chatId,
    createdAt: new Date(2026, 0, 1, 0, index),
    content: `content ${index + 1}`,
    role: index % 2 === 0 ? ('user' as const) : ('assistant' as const),
  }));
}

export interface ListProps {
  messages: Message[];
  loading: boolean;
  messageAppeared: boolean;
  chatId: string | undefined;
  highlightMessageId: string | null;
}

export interface ListHandles {
  userScrolledRef: MutableRefObject<boolean>;
  centeredHighlightRef: MutableRefObject<string | null>;
  scrollToMessageRef: MutableRefObject<((index: number) => void) | null>;
  scrollToBottomRef: MutableRefObject<(() => void) | null>;
  onUserScrolledChange: Mock<(userScrolled: boolean) => void>;
}

type OptionalHandle = 'scrollToMessageRef' | 'scrollToBottomRef' | 'onUserScrolledChange';

/**
 * Renders the list with default props; `update` re-renders it with some of them changed; `omit` leaves optional
 * handles out; `centeredHighlight` is the highlight the page says it already centred.
 */
export function renderList(
  initial: Partial<ListProps> = {},
  omit: readonly OptionalHandle[] = [],
  centeredHighlight: string | null = null,
) {
  const handles: ListHandles = {
    userScrolledRef: { current: false },
    centeredHighlightRef: { current: centeredHighlight },
    scrollToMessageRef: { current: null },
    scrollToBottomRef: { current: null },
    onUserScrolledChange: vi.fn<(userScrolled: boolean) => void>(),
  };
  const column = document.createElement('div');
  column.setAttribute('data-column', 'message-column');
  const containerRef: RefObject<HTMLDivElement | null> = { current: column };
  let props: ListProps = {
    messages: makeMessages(30),
    loading: false,
    messageAppeared: true,
    chatId: freshChatId(),
    highlightMessageId: null,
    ...initial,
  };
  const tree = () => (
    <VirtualMessageList
      {...props}
      userScrolledRef={handles.userScrolledRef}
      centeredHighlightRef={handles.centeredHighlightRef}
      scrollToMessageRef={omit.includes('scrollToMessageRef') ? undefined : handles.scrollToMessageRef}
      scrollToBottomRef={omit.includes('scrollToBottomRef') ? undefined : handles.scrollToBottomRef}
      onUserScrolledChange={omit.includes('onUserScrolledChange') ? undefined : handles.onUserScrolledChange}
      containerRef={containerRef}
    />
  );
  const view = render(tree());
  const scroller = () => view.container.firstElementChild as HTMLDivElement;
  return {
    ...view,
    ...handles,
    scroller,
    chatId: () => props.chatId,
    update: (next: Partial<ListProps>) => {
      props = { ...props, ...next };
      view.rerender(tree());
    },
  };
}

/** Gives the scroll container its box metrics; jsdom lays nothing out. */
export function setScrollMetrics(
  element: HTMLElement,
  metrics: { top?: number; height?: number; client?: number },
): void {
  const define = (name: 'scrollTop' | 'scrollHeight' | 'clientHeight', value: number | undefined) => {
    if (value !== undefined) {
      Object.defineProperty(element, name, { configurable: true, writable: true, value });
    }
  };
  define('scrollTop', metrics.top);
  define('scrollHeight', metrics.height);
  define('clientHeight', metrics.client);
}

/** Moves the container to `top` and fires its scroll event. */
export function scrollTo(element: HTMLElement, top: number): void {
  setScrollMetrics(element, { top });
  fireEvent.scroll(element);
}

export function readMirror(chatId: string): ScrollFollowMirrorEntry | null {
  const raw = sessionStorage.getItem(`${MIRROR_KEY_PREFIX}${chatId}`);
  return raw ? (JSON.parse(raw) as ScrollFollowMirrorEntry) : null;
}

export function writeMirror(chatId: string, entry: Omit<ScrollFollowMirrorEntry, 'timestamp'>): void {
  sessionStorage.setItem(`${MIRROR_KEY_PREFIX}${chatId}`, JSON.stringify({ ...entry, timestamp: Date.now() }));
}
