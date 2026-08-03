'use client';

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const mockRouterPush = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ back: vi.fn(), push: mockRouterPush }),
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

vi.mock('@/components/features/copilot/RunStatusChip', () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock('@/components/features/copilot/SessionAdvisorPanel', () => ({
  __esModule: true,
  default: () => null,
}));

let chatStoreState = {
  messages: [{ role: 'assistant', messageId: 'm1', content: 'hello' }],
  loading: true,
  stopMessage: vi.fn(),
  isMessagesLoaded: true,
  sendMessage: vi.fn(),
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

vi.mock('@/components/features/chat-window/MobileStatusApprovalsSection', () => ({
  MobileStatusApprovalsSection: () => null,
}));

vi.mock('@/components/features/chat-window/MobileStatusMessageBody', () => ({
  MobileStatusMessageBody: () => null,
}));

import MobileStatusBoard from '../MobileStatusBoard';

describe('MobileStatusBoard full conversation link', () => {
  beforeEach(() => {
    mockRouterPush.mockClear();
    chatStoreState = {
      messages: [{ role: 'assistant', messageId: 'm1', content: 'hello' }],
      loading: true,
      stopMessage: vi.fn(),
      isMessagesLoaded: true,
      sendMessage: vi.fn(),
      steerMessage: vi.fn(),
      loadMessages: vi.fn(),
    };
  });

  it('shows viewFull link while run is loading and navigates to main chat', () => {
    render(<MobileStatusBoard chatId="chat-abc" />);

    const link = screen.getByTestId('mobile-command-view-full-conversation');
    fireEvent.click(link);

    expect(mockRouterPush).toHaveBeenCalledWith('/chat-abc');
  });

  it('hides viewFull link when run is not loading', () => {
    chatStoreState.loading = false;
    render(<MobileStatusBoard chatId="chat-abc" />);

    expect(screen.queryByTestId('mobile-command-view-full-conversation')).toBeNull();
  });
});
