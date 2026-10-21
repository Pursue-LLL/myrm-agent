/** @vitest-environment jsdom */
import { render } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import useChatStore from '@/store/useChatStore';
import type { Message } from '@/store/chat/types';
import en from '../../../../../locales/en.json';
import zh from '../../../../../locales/zh.json';
import ChatWindow from '../ChatWindow';

type InspectorHandler = (instruction: string, refId: string | null) => void;

const satellites = vi.hoisted(() => ({
  onBrowserInstruction: null as InspectorHandler | null,
  onDesktopInstruction: null as InspectorHandler | null,
}));

const navigationMock = vi.hoisted(() => ({
  replace: vi.fn(),
  push: vi.fn(),
  prefetch: vi.fn(),
  searchParams: new URLSearchParams(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: navigationMock.replace,
    push: navigationMock.push,
    prefetch: navigationMock.prefetch,
  }),
  useSearchParams: () => navigationMock.searchParams,
  usePathname: () => '/',
}));

// The global setup stubs next-intl with an identity translator; this suite asserts the real locale copy.
vi.mock('next-intl', async (importOriginal) => importOriginal<typeof import('next-intl')>());

vi.mock('../Chat', () => ({ default: () => <div data-testid="chat-view">Chat Stream</div> }));
vi.mock('../EmptyChat', () => ({ default: () => <textarea aria-label="message input" /> }));
vi.mock('../MessageListSkeleton', () => ({
  default: () => <div aria-label="Loading messages">skeleton</div>,
}));
vi.mock('../ToolApprovalDialog', () => ({ default: () => null }));
vi.mock('../ToolApprovalExpiryWatcher', () => ({ default: () => null }));
vi.mock('../AgentInfoBanner', () => ({ default: () => null }));
vi.mock('../YoloModeBanner', () => ({ default: () => null }));
vi.mock('../EStopBanner', () => ({ default: () => null }));
vi.mock('../ExtensionDisconnectedBanner', () => ({ default: () => null }));
vi.mock('../ExtensionTakeoverBanner', () => ({ default: () => null }));
vi.mock('../ChatWindowSatellites', () => ({
  default: (props: { onInspectorInstruction: InspectorHandler; onDesktopInspectorInstruction: InspectorHandler }) => {
    satellites.onBrowserInstruction = props.onInspectorInstruction;
    satellites.onDesktopInstruction = props.onDesktopInspectorInstruction;
    return null;
  },
  GoalControlPlane: () => null,
  GoalStatusCard: () => null,
  LifeStatusCapsule: () => null,
}));
vi.mock('../ParentChatLink', () => ({ ParentChatLink: () => null }));
vi.mock('../ChatCronLink', () => ({ ChatCronLink: () => null }));
vi.mock('../WorkingStateBadge', () => ({ default: () => null }));
vi.mock('../SubagentPromptButton', () => ({ default: () => null }));
vi.mock('../subagent/SubagentDashboard', () => ({ default: () => null }));
vi.mock('@/components/features/artifacts/ArtifactPortal', () => ({ default: () => null }));
vi.mock('@/components/features/app-shell/VisualDesktopToggle', () => ({ VisualDesktopToggle: () => null }));
vi.mock('@/components/features/message-actions/SessionRevertButton', () => ({ default: () => null }));
vi.mock('@/components/features/copilot/RunStatusChip', () => ({ default: () => null }));
vi.mock('@/components/features/copilot/SessionAdvisorPanel', () => ({ default: () => null }));
vi.mock('@/components/features/memory/pending/PendingMemoryBadge', () => ({ default: () => null }));
vi.mock('@/components/features/memory/pending/PendingMemoryDialog', () => ({ default: () => null }));
vi.mock('@/components/features/settings/sections/system/ExecutionTraceTimeline', () => ({ default: () => null }));

// Only the inspector copy is under test; other namespaces fall back to their key paths.
const CATALOGS = {
  en: { chat: { inspector: en.chat.inspector } },
  zh: { chat: { inspector: zh.chat.inspector } },
} as const;

const ignoreIntlError = () => undefined;
const originalSendMessage = useChatStore.getState().sendMessage;
let sendMessageMock = vi.fn<typeof originalSendMessage>();

function renderWindow(locale: keyof typeof CATALOGS) {
  render(
    <NextIntlClientProvider locale={locale} messages={CATALOGS[locale]} onError={ignoreIntlError}>
      <ChatWindow id="session-inspector-1" />
    </NextIntlClientProvider>,
  );
}

function requireHandler(handler: InspectorHandler | null): InspectorHandler {
  if (!handler) {
    throw new Error('ChatWindowSatellites did not receive the inspector handler');
  }
  return handler;
}

describe('ChatWindow inspector instructions', () => {
  beforeEach(() => {
    vi.useRealTimers();
    satellites.onBrowserInstruction = null;
    satellites.onDesktopInstruction = null;
    navigationMock.searchParams = new URLSearchParams();
    sendMessageMock = vi.fn<typeof originalSendMessage>().mockResolvedValue(true);
    useChatStore.setState({
      chatId: 'session-inspector-1',
      inputMessage: '',
      messages: [{ id: 'msg-1', role: 'user', content: 'hello' } as unknown as Message],
      isMessagesLoaded: true,
      loading: false,
      messageAppeared: true,
      notFound: false,
      loadError: false,
      sendMessage: sendMessageMock,
    });
  });

  afterEach(() => {
    useChatStore.setState({ sendMessage: originalSendMessage });
  });

  it.each([
    ['en', 'click it', '[Browser Inspector] I selected the page element [ref=e12]: click it'],
    ['en', '', '[Browser Inspector] I selected the page element [ref=e12]: Please act on this element'],
    ['zh', '点击它', '[Browser Inspector] 我选中了页面元素 [ref=e12]，点击它'],
    ['zh', '', '[Browser Inspector] 我选中了页面元素 [ref=e12]，请对此元素执行操作'],
  ] as const)('words a selected page element for %s users (instruction %j)', (locale, instruction, expected) => {
    renderWindow(locale);

    requireHandler(satellites.onBrowserInstruction)(instruction, 'e12');

    expect(sendMessageMock).toHaveBeenCalledTimes(1);
    expect(sendMessageMock).toHaveBeenCalledWith(expected);
  });

  it.each([
    ['en', 'open it', '[Desktop Inspector] I selected the desktop element [@e7]: open it'],
    ['en', '', '[Desktop Inspector] I selected the desktop element [@e7]: Please act on this element'],
    ['zh', '打开它', '[Desktop Inspector] 我选中了桌面元素 [@e7]，打开它'],
    ['zh', '', '[Desktop Inspector] 我选中了桌面元素 [@e7]，请对此元素执行操作'],
  ] as const)('words a selected desktop element for %s users (instruction %j)', (locale, instruction, expected) => {
    renderWindow(locale);

    requireHandler(satellites.onDesktopInstruction)(instruction, 'e7');

    expect(sendMessageMock).toHaveBeenCalledTimes(1);
    expect(sendMessageMock).toHaveBeenCalledWith(expected);
  });

  it('passes a free-form instruction through untouched when no element is selected', () => {
    renderWindow('zh');

    requireHandler(satellites.onBrowserInstruction)('向下滚动', null);
    requireHandler(satellites.onDesktopInstruction)('向下滚动', null);

    expect(sendMessageMock.mock.calls).toEqual([['[Browser Inspector] 向下滚动'], ['[Desktop Inspector] 向下滚动']]);
  });

  it('does not reinterpret ICU syntax typed by the user', () => {
    renderWindow('en');

    requireHandler(satellites.onBrowserInstruction)("type {name} and don't stop", 'e12');

    expect(sendMessageMock).toHaveBeenCalledWith(
      "[Browser Inspector] I selected the page element [ref=e12]: type {name} and don't stop",
    );
  });
});
