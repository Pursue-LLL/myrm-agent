/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockRouter, mockRemoteAccess, stableT, stableLocale } = vi.hoisted(() => ({
  mockRouter: { push: vi.fn(), back: vi.fn() },
  mockRemoteAccess: {
    getMobileSessions: vi.fn(),
    getSpawnOptions: vi.fn(),
    spawnMobileSession: vi.fn(),
  },
  stableT: (key: string) => key,
  stableLocale: 'zh',
}));

vi.mock('next/navigation', () => ({
  useRouter: () => mockRouter,
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => stableLocale,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconActivity: () => null,
  IconArrowRight: () => null,
  IconChevronUp: () => null,
  IconPlus: () => null,
}));

vi.mock('@/lib/mobileRemote', () => ({
  scheduleMobilePairRefresh: () => vi.fn(),
  storeMobilePairToken: vi.fn(),
}));

vi.mock('@/lib/e2ee/useE2EEStatus', () => ({
  useE2EEStatus: () => ({ isReady: false, isVerified: false }),
}));

vi.mock('@/components/features/e2ee/E2EESecurityPanel', () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock('@/components/agent/builtin-agent-i18n', () => ({
  getBuiltinAgentName: (id: string) => id,
}));

vi.mock('@/services/remoteAccess', () => ({
  remoteAccessService: mockRemoteAccess,
}));

import MobileSessionHub from '../MobileSessionHub';

function getTextarea(): HTMLTextAreaElement {
  return screen.getByRole('textbox') as HTMLTextAreaElement;
}

async function openTaskForm(): Promise<void> {
  await act(async () => {
    fireEvent.click(screen.getByText('newTask'));
  });
}

describe('MobileSessionHub task composition', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    mockRemoteAccess.getMobileSessions.mockResolvedValue({ activeSessions: [] });
    mockRemoteAccess.getSpawnOptions.mockResolvedValue({
      agents: [{ id: 'agent-a', name: 'Agent A', avatar: null }],
      projects: [],
      defaultAgentId: 'agent-a',
    });
    mockRemoteAccess.spawnMobileSession.mockResolvedValue({ token: 'tok', mobilePath: '/mobile/status/new' });
  });

  it('creates a remote session on a plain Enter submit', async () => {
    render(<MobileSessionHub />);
    await openTaskForm();

    fireEvent.change(getTextarea(), { target: { value: '调研竞品定价' } });
    await act(async () => {
      fireEvent.keyDown(getTextarea(), { key: 'Enter' });
    });

    expect(mockRemoteAccess.spawnMobileSession).toHaveBeenCalledWith(
      expect.objectContaining({ initialMessage: '调研竞品定价' }),
    );
  });

  it('does not create a session when Enter only confirms an IME candidate', async () => {
    render(<MobileSessionHub />);
    await openTaskForm();

    fireEvent.change(getTextarea(), { target: { value: '调研竞品定价' } });
    await act(async () => {
      fireEvent.keyDown(getTextarea(), { key: 'Enter', isComposing: true });
    });

    expect(mockRemoteAccess.spawnMobileSession).not.toHaveBeenCalled();
  });

  it('does not create a session on the legacy IME keyCode 229 signal', async () => {
    render(<MobileSessionHub />);
    await openTaskForm();

    fireEvent.change(getTextarea(), { target: { value: '调研竞品定价' } });
    await act(async () => {
      fireEvent.keyDown(getTextarea(), { key: 'Enter', keyCode: 229, isComposing: false });
    });

    expect(mockRemoteAccess.spawnMobileSession).not.toHaveBeenCalled();
  });

  it('keeps Shift+Enter as a newline instead of submitting', async () => {
    render(<MobileSessionHub />);
    await openTaskForm();

    fireEvent.change(getTextarea(), { target: { value: '第一段' } });
    await act(async () => {
      fireEvent.keyDown(getTextarea(), { key: 'Enter', shiftKey: true });
    });

    expect(mockRemoteAccess.spawnMobileSession).not.toHaveBeenCalled();
  });
});
