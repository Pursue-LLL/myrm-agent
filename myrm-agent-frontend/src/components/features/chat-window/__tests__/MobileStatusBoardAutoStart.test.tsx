'use client';

import { render, act } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

const mockSendMessage = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ back: vi.fn(), push: vi.fn() }),
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('zustand/react/shallow', () => ({
  useShallow: (fn: unknown) => fn,
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

vi.mock('@/store/chat/goals/usePlanStore', () => ({
  usePlanStore: () => ({ plan: null }),
}));

vi.mock('@/store/chat/goals/useGoalStore', () => ({
  useGoalStore: () => null,
}));

let chatStoreState = {
  messages: [],
  loading: false,
  stopMessage: vi.fn(),
  isMessagesLoaded: true,
  sendMessage: mockSendMessage,
  steerMessage: vi.fn(),
  loadMessages: vi.fn(),
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
  return { __esModule: true, default: fn };
});

vi.mock('@/store/useDesktopInspectorStore', () => {
  const fn = (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ viewData: null, isSnapshotLoading: false });
  return { __esModule: true, default: fn };
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

describe('MobileStatusBoard autoStart', () => {
  beforeEach(() => {
    mockSendMessage.mockClear();
    chatStoreState = {
      messages: [],
      loading: false,
      stopMessage: vi.fn(),
      isMessagesLoaded: true,
      sendMessage: mockSendMessage,
      steerMessage: vi.fn(),
      loadMessages: vi.fn(),
    };
    sessionStorage.clear();
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  it('sends autoStart message from sessionStorage when messages are loaded', async () => {
    sessionStorage.setItem('myrm_mobile_autostart_message', 'Research AI trends');
    await act(async () => {
      render(<MobileStatusBoard chatId="test-chat-1" />);
    });
    expect(mockSendMessage).toHaveBeenCalledWith('Research AI trends');
    expect(sessionStorage.getItem('myrm_mobile_autostart_message')).toBeNull();
  });

  it('does not fire autoStart when no sessionStorage item exists', async () => {
    await act(async () => {
      render(<MobileStatusBoard chatId="test-chat-2" />);
    });
    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  it('does not fire autoStart when messages are still loading', async () => {
    chatStoreState.isMessagesLoaded = false;
    sessionStorage.setItem('myrm_mobile_autostart_message', 'Should not fire');
    await act(async () => {
      render(<MobileStatusBoard chatId="test-chat-3" />);
    });
    expect(mockSendMessage).not.toHaveBeenCalled();
    expect(sessionStorage.getItem('myrm_mobile_autostart_message')).toBe('Should not fire');
  });

  it('does not fire autoStart when agent is already running', async () => {
    chatStoreState.loading = true;
    sessionStorage.setItem('myrm_mobile_autostart_message', 'Should not fire');
    await act(async () => {
      render(<MobileStatusBoard chatId="test-chat-4" />);
    });
    expect(mockSendMessage).not.toHaveBeenCalled();
  });
});
