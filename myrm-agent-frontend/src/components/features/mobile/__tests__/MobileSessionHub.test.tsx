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
  IconCheckCircle: () => null,
  IconChevronUp: () => null,
  IconClock: () => null,
  IconPlus: () => null,
  IconUsers: () => null,
  IconX: () => null,
  IconShieldCheck: () => null,
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
  getBuiltinAgentName: (_id: string, name: string) => name,
}));

vi.mock('@/services/remoteAccess', () => ({
  remoteAccessService: mockRemoteAccess,
}));

const { mockCancelActiveChatAgent, mockShowI18nToast } = vi.hoisted(() => ({
  mockCancelActiveChatAgent: vi.fn(),
  mockShowI18nToast: vi.fn(),
}));

vi.mock('@/services/chat', () => ({
  cancelActiveChatAgent: mockCancelActiveChatAgent,
}));

vi.mock('@/services/i18nToastService', () => ({
  showI18nToast: mockShowI18nToast,
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
    mockRemoteAccess.getMobileSessions.mockResolvedValue({
      activeSessions: [],
      recentSessions: [],
      maxConcurrent: 3,
      availableSlots: 3,
    });
    mockRemoteAccess.getSpawnOptions.mockResolvedValue({
      agents: [{ id: 'agent-a', name: 'Agent A', avatar: null }],
      projects: [],
      defaultAgentId: 'agent-a',
    });
    mockRemoteAccess.spawnMobileSession.mockResolvedValue({ token: 'tok', mobilePath: '/mobile/status/new' });
  });

  it('shows the curtain shield when the workstation curtain is active', async () => {
    mockRemoteAccess.getMobileSessions.mockResolvedValue({
      activeSessions: [],
      recentSessions: [],
      maxConcurrent: 3,
      availableSlots: 3,
      curtain: { available: true, active: true, autoEngaged: true },
    });

    render(<MobileSessionHub />);

    expect(await screen.findByText('curtainActive')).toBeInTheDocument();
  });

  it('hides the curtain shield when the curtain is inactive or unavailable', async () => {
    mockRemoteAccess.getMobileSessions.mockResolvedValue({
      activeSessions: [],
      recentSessions: [],
      maxConcurrent: 3,
      availableSlots: 3,
      curtain: { available: true, active: false },
    });

    render(<MobileSessionHub />);

    await screen.findByText('badge');
    expect(screen.queryByText('curtainActive')).not.toBeInTheDocument();
  });

  it('hides the curtain shield on non-desktop deployments', async () => {
    mockRemoteAccess.getMobileSessions.mockResolvedValue({
      activeSessions: [],
      recentSessions: [],
      maxConcurrent: 3,
      availableSlots: 3,
      curtain: { available: false, active: false },
    });

    render(<MobileSessionHub />);

    await screen.findByText('badge');
    expect(screen.queryByText('curtainActive')).not.toBeInTheDocument();
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

describe('MobileSessionHub sections and concurrency gating', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    mockRemoteAccess.getSpawnOptions.mockResolvedValue({
      agents: [{ id: 'agent-a', name: 'Agent A', avatar: null }],
      projects: [],
      defaultAgentId: 'agent-a',
    });
    mockRemoteAccess.spawnMobileSession.mockResolvedValue({ token: 'tok', mobilePath: '/mobile/status/new' });
  });

  it('renders running and recently finished sections with agent names and slot badge', async () => {
    mockRemoteAccess.getMobileSessions.mockResolvedValue({
      activeSessions: [
        { chatId: 'c1', agentId: 'a1', agentType: 'general', agentName: 'Research Agent', elapsedSeconds: 42 },
      ],
      recentSessions: [
        { chatId: 'c2', title: 'Finished Report', agentId: 'a1', agentName: 'Research Agent', updatedAt: new Date().toISOString() },
      ],
      maxConcurrent: 3,
      availableSlots: 2,
    });

    render(<MobileSessionHub />);
    await act(async () => {});

    expect(screen.getByText('sectionActive')).toBeDefined();
    expect(screen.getByText('sectionRecent')).toBeDefined();
    // Active card title and recent card agent line both carry the display name.
    expect(screen.getAllByText('Research Agent').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('Finished Report')).toBeDefined();
    expect(screen.getByText('slotsBadge')).toBeDefined();
  });

  it('blocks spawn with a warning when all parallel slots are busy', async () => {
    mockRemoteAccess.getMobileSessions.mockResolvedValue({
      activeSessions: [
        { chatId: 'c1', agentId: 'a1', agentType: 'general', agentName: 'Research Agent', elapsedSeconds: 42 },
      ],
      recentSessions: [],
      maxConcurrent: 1,
      availableSlots: 0,
    });

    render(<MobileSessionHub />);
    await act(async () => {});
    await openTaskForm();

    fireEvent.change(getTextarea(), { target: { value: '再开一个任务' } });
    await act(async () => {
      fireEvent.keyDown(getTextarea(), { key: 'Enter' });
    });

    expect(screen.getByText('slotsFull')).toBeDefined();
    expect(mockRemoteAccess.spawnMobileSession).not.toHaveBeenCalled();
  });
});

describe('MobileSessionHub stop from running card', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    mockRemoteAccess.getMobileSessions.mockResolvedValue({
      activeSessions: [
        { chatId: 'c1', agentId: 'a1', agentType: 'general', agentName: 'Research Agent', elapsedSeconds: 42 },
      ],
      recentSessions: [],
      maxConcurrent: 3,
      availableSlots: 2,
    });
    mockRemoteAccess.getSpawnOptions.mockResolvedValue({
      agents: [{ id: 'agent-a', name: 'Agent A', avatar: null }],
      projects: [],
      defaultAgentId: 'agent-a',
    });
    mockRemoteAccess.spawnMobileSession.mockResolvedValue({ token: 'tok', mobilePath: '/mobile/status/new' });
    mockCancelActiveChatAgent.mockResolvedValue({ cancelled: true, chat_id: 'c1' });
  });

  it('stops a running session from the card and refreshes the list', async () => {
    render(<MobileSessionHub />);
    await act(async () => {});

    const callsBefore = mockRemoteAccess.getMobileSessions.mock.calls.length;
    await act(async () => {
      fireEvent.click(screen.getByText('stop'));
    });

    expect(mockCancelActiveChatAgent).toHaveBeenCalledWith('c1');
    expect(mockShowI18nToast).toHaveBeenCalledWith('agent.mobileCommand.stopTaskSuccess', undefined, {
      type: 'success',
    });
    // A successful stop immediately pulls a fresh session list.
    expect(mockRemoteAccess.getMobileSessions.mock.calls.length).toBeGreaterThan(callsBefore);
  });

  it('signals a warning toast when stopping fails', async () => {
    mockCancelActiveChatAgent.mockRejectedValue(new Error('cancel rejected'));

    render(<MobileSessionHub />);
    await act(async () => {});

    await act(async () => {
      fireEvent.click(screen.getByText('stop'));
    });

    expect(mockShowI18nToast).toHaveBeenCalledWith('agent.mobileCommand.stopTaskFailed', undefined, {
      type: 'warning',
    });
  });
});
