/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { toastError } = vi.hoisted(() => ({ toastError: vi.fn() }));
const mockSendMessage = vi.fn<(text: string) => Promise<boolean>>();
const mockSteerMessage = vi.fn<(text: string) => Promise<boolean>>();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ back: vi.fn(), push: vi.fn() }),
}));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('zustand/react/shallow', () => ({
  useShallow: (fn: unknown) => fn,
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: { error: toastError, info: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

vi.mock('@/lib/mobileRemote', () => ({
  scheduleMobilePairRefresh: () => vi.fn(),
}));

vi.mock('@/lib/e2ee/useE2EEStatus', () => ({
  useE2EEStatus: () => ({ isReady: false, isVerified: false }),
}));

vi.mock('@/components/features/e2ee/E2EESecurityPanel', () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock('@/components/features/message-input-actions/SpeechInputButton', () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock('@/lib/approval/visualApprovalSurface', () => ({
  partitionApprovalQueue: () => ({ inlineRequests: [], modalRequests: [] }),
}));

vi.mock('@/hooks/approval/useToolApprovalResolve', () => ({
  useToolApprovalResolve: () => ({
    resolveRequest: vi.fn(),
    approveAll: vi.fn(),
    rejectAll: vi.fn(),
    isLoading: false,
  }),
}));

vi.mock('@/hooks/approval/useVisualApprovalSnapshot', () => ({
  useVisualApprovalSnapshot: () => ({
    status: 'idle',
    snapshotFetchFailed: false,
    retrySnapshot: vi.fn(),
  }),
}));

vi.mock('@/components/features/chat-window/goals/useGoalPlanSync', () => ({
  useGoalPlanSync: vi.fn(),
}));

vi.mock('@/components/features/chat-window/goals/useGoalSync', () => ({
  useGoalSync: vi.fn(),
}));

vi.mock('@/store/chat/goals/usePlanStore', () => ({
  usePlanStore: () => ({ plan: null }),
}));

vi.mock('@/store/chat/goals/useGoalStore', () => ({
  useGoalStore: () => null,
}));

let chatStoreState: Record<string, unknown> = {
  chatId: 'stop-chat-1',
  sessionStatuses: {} as Record<string, string>,
  messages: [],
  loading: false,
  abortController: null as AbortController | null,
  stopMessage: vi.fn(),
  isMessagesLoaded: true,
  sendMessage: mockSendMessage,
  steerMessage: mockSteerMessage,
};

vi.mock('@/store/useChatStore', () => {
  const fn = (selector: (s: typeof chatStoreState) => unknown) => selector(chatStoreState);
  fn.getState = () => ({ loadMessages: vi.fn() });
  return { __esModule: true, default: fn };
});

vi.mock('@/store/useToolApprovalStore', () => {
  const fn = () => [];
  return { __esModule: true, default: fn };
});

vi.mock('@/store/useBrowserInspectorStore', () => {
  const fn = (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ viewData: null, isSnapshotLoading: false });
  return { __esModule: true, default: fn, selectScopedBrowserViewData: () => null };
});

vi.mock('@/store/useDesktopInspectorStore', () => {
  const fn = (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ viewData: null, isSnapshotLoading: false });
  return { __esModule: true, default: fn, selectScopedDesktopViewData: () => null };
});

vi.mock('@/components/primitives/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => {
    const { variant: _v, size: _s, ...rest } = props;
    return <button {...(rest as React.ButtonHTMLAttributes<HTMLButtonElement>)}>{children as React.ReactNode}</button>;
  },
}));

vi.mock('@/components/features/chat-window/mobile/MobileStatusApprovalsSection', () => ({
  MobileStatusApprovalsSection: () => null,
}));

vi.mock('@/components/features/chat-window/mobile/MobileStatusMessageBody', () => ({
  MobileStatusMessageBody: () => null,
}));

import MobileStatusBoard from '../mobile/MobileStatusBoard';

const COMMAND = '把结论整理成一页纸';

function getInput(): HTMLTextAreaElement {
  return screen.getByRole('textbox') as HTMLTextAreaElement;
}

async function submitCommand(text: string): Promise<void> {
  fireEvent.change(getInput(), { target: { value: text } });
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'send' }));
  });
}

describe('MobileStatusBoard command submit', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
    mockSendMessage.mockResolvedValue(true);
    mockSteerMessage.mockResolvedValue(true);
    chatStoreState = { ...chatStoreState, loading: false };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('sends a new command while the agent is idle and clears the input', async () => {
    await act(async () => {
      render(<MobileStatusBoard chatId="command-chat-1" />);
    });

    await submitCommand(COMMAND);

    expect(mockSendMessage).toHaveBeenCalledWith(COMMAND);
    expect(mockSteerMessage).not.toHaveBeenCalled();
    expect(toastError).not.toHaveBeenCalled();
    expect(getInput().value).toBe('');
  });

  it('steers the running agent instead of starting a new turn', async () => {
    chatStoreState = { ...chatStoreState, loading: true };
    await act(async () => {
      render(<MobileStatusBoard chatId="command-chat-2" />);
    });

    await submitCommand(COMMAND);

    expect(mockSteerMessage).toHaveBeenCalledWith(COMMAND);
    expect(mockSendMessage).not.toHaveBeenCalled();
    expect(getInput().value).toBe('');
  });

  it('tells the user and keeps the text when the running agent refuses the steer', async () => {
    chatStoreState = { ...chatStoreState, loading: true };
    mockSteerMessage.mockResolvedValue(false);
    await act(async () => {
      render(<MobileStatusBoard chatId="command-chat-3" />);
    });

    await submitCommand(COMMAND);

    expect(toastError).toHaveBeenCalledWith('commandNotAccepted');
    expect(getInput().value).toBe(COMMAND);
  });

  it('treats a busy rejection of a new command as refused and gives the text back', async () => {
    const busy = new Error('Agent is busy');
    busy.name = 'AgentBusyError';
    mockSendMessage.mockRejectedValue(busy);
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    await act(async () => {
      render(<MobileStatusBoard chatId="command-chat-4" />);
    });

    await submitCommand(COMMAND);

    expect(toastError).toHaveBeenCalledWith('commandNotAccepted');
    expect(getInput().value).toBe(COMMAND);
  });
});

describe('MobileStatusBoard stop button', () => {
  const stopMessage = vi.fn();
  const stopButton = () => screen.queryByRole('button', { name: 'stopTask' });

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sessionStatuses({});
    chatStoreState = { ...chatStoreState, loading: false, abortController: null, stopMessage };
  });

  function sessionStatuses(statuses: Record<string, string>): void {
    chatStoreState = { ...chatStoreState, chatId: 'stop-chat-1', sessionStatuses: statuses };
  }

  it('offers no stop while the agent is idle', async () => {
    await act(async () => {
      render(<MobileStatusBoard chatId="stop-chat-1" />);
    });

    expect(stopButton()).toBeNull();
  });

  it('offers stop for a turn this client started', async () => {
    chatStoreState = { ...chatStoreState, loading: true, abortController: new AbortController() };
    await act(async () => {
      render(<MobileStatusBoard chatId="stop-chat-1" />);
    });

    expect(stopButton()).not.toBeNull();
  });

  it('offers no stop while the history of the chat loads: no turn is attached yet, so Stop would reach nothing', async () => {
    chatStoreState = { ...chatStoreState, loading: true, abortController: null };
    await act(async () => {
      render(<MobileStatusBoard chatId="stop-chat-1" />);
    });

    expect(stopButton()).toBeNull();
  });

  it('offers stop for a turn the server started itself, such as a wake after background work', async () => {
    sessionStatuses({ 'stop-chat-1': 'generating' });
    await act(async () => {
      render(<MobileStatusBoard chatId="stop-chat-1" />);
    });

    fireEvent.click(stopButton() as HTMLElement);

    expect(stopMessage).toHaveBeenCalledTimes(1);
  });

  it('offers no stop for a turn running in another chat', async () => {
    sessionStatuses({ 'other-chat': 'generating' });
    await act(async () => {
      render(<MobileStatusBoard chatId="stop-chat-1" />);
    });

    expect(stopButton()).toBeNull();
  });
});
