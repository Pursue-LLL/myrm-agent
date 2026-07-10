'use client';

import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

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

vi.mock('@/components/features/message-box/progress-steps/ProgressSteps', () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock('@/components/features/chat-window/approval/VisualApprovalRequestRenderer', () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock('@/components/features/chat-window/SingleApprovalCard', () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock('@/lib/approval/visualApprovalSurface', () => ({
  partitionApprovalQueue: () => ({ inlineRequests: [], modalRequests: [] }),
}));

vi.mock('@/hooks/useToolApprovalResolve', () => ({
  useToolApprovalResolve: () => ({
    resolveRequest: vi.fn(),
    approveAll: vi.fn(),
    rejectAll: vi.fn(),
    isLoading: false,
  }),
}));

vi.mock('@/hooks/useVisualApprovalSnapshot', () => ({
  useVisualApprovalSnapshot: () => ({
    status: 'idle',
    snapshotFetchFailed: false,
    retrySnapshot: vi.fn(),
  }),
}));

vi.mock('@/components/features/chat-window/goals/GoalPlanStepsList', () => ({
  GoalPlanStepsList: () => null,
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

vi.mock('@/store/useChatStore', () => {
  const store = {
    messages: [
      { role: 'assistant', messageId: '1', content: 'done', progressSteps: [], thinkingItems: [] },
    ],
    loading: false,
    stopMessage: vi.fn(),
    isMessagesLoaded: true,
    sendMessage: vi.fn(),
    steerMessage: vi.fn(),
    loadMessages: vi.fn(),
    getState: () => ({ loadMessages: vi.fn() }),
  };
  const fn = (selector: (s: typeof store) => unknown) => selector(store);
  fn.getState = store.getState;
  return { __esModule: true, default: fn };
});

vi.mock('@/store/useToolApprovalStore', () => {
  const fn = () => [];
  return { __esModule: true, default: fn };
});

const _browserState = {
  viewData: null as null | { screenshotBase64: string; mimeType: string; pageUrl: string; updatedAt: number },
  isSnapshotLoading: false,
};

const _desktopState = {
  viewData: null as null | {
    screenshotBase64: string; mimeType: string; windowTitle: string;
    appName: string; updatedAt: number;
  },
  isSnapshotLoading: false,
};

vi.mock('@/store/useBrowserInspectorStore', () => {
  const fn = (selector: (s: typeof _browserState) => unknown) => selector(_browserState);
  return { __esModule: true, default: fn };
});

vi.mock('@/store/useDesktopInspectorStore', () => {
  const fn = (selector: (s: typeof _desktopState) => unknown) => selector(_desktopState);
  return { __esModule: true, default: fn };
});

vi.mock('@/components/primitives/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: string; size?: string }) => (
    <button {...props}>{children}</button>
  ),
}));

import MobileStatusBoard from '../MobileStatusBoard';

describe('MobileStatusBoard Live Preview', () => {
  beforeEach(() => {
    _browserState.viewData = null;
    _browserState.isSnapshotLoading = false;
    _desktopState.viewData = null;
    _desktopState.isSnapshotLoading = false;
  });

  afterEach(() => {
    document.body.style.overflow = '';
  });

  it('does not render Live Preview card when no viewData', () => {
    render(<MobileStatusBoard chatId="test" />);
    expect(screen.queryByText('livePreview')).toBeNull();
  });

  it('renders browser pageUrl when browser viewData present', () => {
    _browserState.viewData = {
      screenshotBase64: 'abc',
      mimeType: 'image/png',
      pageUrl: 'https://example.com',
      updatedAt: Date.now(),
    };
    render(<MobileStatusBoard chatId="test" />);
    expect(screen.getByText('livePreview')).toBeInTheDocument();
    expect(screen.getByText('https://example.com')).toBeInTheDocument();
  });

  it('renders Desktop windowTitle (not pageUrl) when desktop viewData present', () => {
    _desktopState.viewData = {
      screenshotBase64: 'abc',
      mimeType: 'image/png',
      windowTitle: 'Figma - Design',
      appName: 'Figma',
      updatedAt: Date.now(),
    };
    render(<MobileStatusBoard chatId="test" />);
    expect(screen.getByText('livePreview')).toBeInTheDocument();
    expect(screen.getByText('Figma - Design')).toBeInTheDocument();
  });

  it('falls back to appName when windowTitle is empty for desktop', () => {
    _desktopState.viewData = {
      screenshotBase64: 'abc',
      mimeType: 'image/png',
      windowTitle: '',
      appName: 'Excel',
      updatedAt: Date.now(),
    };
    render(<MobileStatusBoard chatId="test" />);
    expect(screen.getByText('Excel')).toBeInTheDocument();
  });

  it('opens Lightbox on screenshot click and locks body scroll', () => {
    _browserState.viewData = {
      screenshotBase64: 'abc',
      mimeType: 'image/png',
      pageUrl: 'https://example.com',
      updatedAt: Date.now(),
    };
    render(<MobileStatusBoard chatId="test" />);
    const imgs = screen.getAllByAltText('livePreview');
    const thumbImg = imgs[0];
    const thumbButton = thumbImg.closest('button')!;
    fireEvent.click(thumbButton);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(document.body.style.overflow).toBe('hidden');
  });

  it('closes Lightbox on Escape key and restores body scroll', () => {
    _browserState.viewData = {
      screenshotBase64: 'abc',
      mimeType: 'image/png',
      pageUrl: 'https://example.com',
      updatedAt: Date.now(),
    };
    render(<MobileStatusBoard chatId="test" />);
    const thumbButton = screen.getAllByAltText('livePreview')[0].closest('button')!;
    fireEvent.click(thumbButton);
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    act(() => {
      fireEvent.keyDown(window, { key: 'Escape' });
    });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.body.style.overflow).toBe('');
  });

  it('does not close Lightbox when clicking the image (stopPropagation)', () => {
    _browserState.viewData = {
      screenshotBase64: 'abc',
      mimeType: 'image/png',
      pageUrl: 'https://example.com',
      updatedAt: Date.now(),
    };
    render(<MobileStatusBoard chatId="test" />);
    const thumbButton = screen.getAllByAltText('livePreview')[0].closest('button')!;
    fireEvent.click(thumbButton);

    const dialog = screen.getByRole('dialog');
    const lightboxImg = dialog.querySelector('img')!;
    fireEvent.click(lightboxImg);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('closes Lightbox when clicking backdrop', () => {
    _browserState.viewData = {
      screenshotBase64: 'abc',
      mimeType: 'image/png',
      pageUrl: 'https://example.com',
      updatedAt: Date.now(),
    };
    render(<MobileStatusBoard chatId="test" />);
    const thumbButton = screen.getAllByAltText('livePreview')[0].closest('button')!;
    fireEvent.click(thumbButton);

    const dialog = screen.getByRole('dialog');
    fireEvent.click(dialog);
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
