/** @vitest-environment jsdom */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockSendMessage = vi.fn();
const mockPush = vi.fn();
const mockGetState = vi.fn();
const mockToast = vi.hoisted(() => ({
  info: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
}));

vi.mock('sonner', () => ({ toast: mockToast }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => mockGetState(),
  },
}));

vi.mock('@/store/useWorkspaceStore', () => ({
  default: {
    getState: () => ({
      panes: [],
      addPane: vi.fn(),
    }),
  },
}));

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}));

import SkillsLearnPanel from '../SkillsLearnPanel';

describe('SkillsLearnPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetState.mockReturnValue({
      chatId: 'chat-1',
      loading: false,
      sendMessage: mockSendMessage,
    });
    mockSendMessage.mockResolvedValue(undefined);
  });

  it('submits composed /learn and navigates to chat', async () => {
    const user = userEvent.setup();
    render(<SkillsLearnPanel />);

    await user.click(screen.getByRole('button', { name: 'settings.skills.learn.panelTitle' }));
    await user.type(screen.getByLabelText('settings.skills.learn.urlLabel'), 'https://docs.example.com/api');
    await user.click(screen.getByRole('button', { name: 'settings.skills.learn.submit' }));

    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalledWith('/learn URL: https://docs.example.com/api');
    });
    expect(mockToast.info).toHaveBeenCalledWith('chat.extractToSkill.started');
    expect(mockPush).toHaveBeenCalledWith('/chat-1');
  });

  it('bootstraps a chat when none is active before submitting', async () => {
    const mockInitializeChat = vi.fn();
    mockGetState.mockReturnValue({
      chatId: null,
      loading: false,
      sendMessage: mockSendMessage,
      initializeChat: mockInitializeChat,
    });

    mockInitializeChat.mockImplementation(() => {
      mockGetState.mockReturnValue({
        chatId: 'bootstrapped-chat',
        loading: false,
        sendMessage: mockSendMessage,
        initializeChat: mockInitializeChat,
      });
    });

    const user = userEvent.setup();
    render(<SkillsLearnPanel />);

    await user.click(screen.getByRole('button', { name: 'settings.skills.learn.panelTitle' }));
    await user.type(screen.getByLabelText('settings.skills.learn.textLabel'), 'release checklist');
    await user.click(screen.getByRole('button', { name: 'settings.skills.learn.submit' }));

    await waitFor(() => {
      expect(mockInitializeChat).toHaveBeenCalledWith(undefined);
    });
    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalledWith('/learn release checklist');
    });
    expect(mockPush).toHaveBeenCalledWith('/bootstrapped-chat');
  });

  it('applies book scenario text and submits correctly', async () => {
    const user = userEvent.setup();
    render(<SkillsLearnPanel />);

    await user.click(screen.getByRole('button', { name: 'settings.skills.learn.panelTitle' }));
    await user.click(screen.getByRole('button', { name: 'settings.skills.learn.scenarios.book.label' }));
    await user.type(screen.getByLabelText('settings.skills.learn.directoryLabel'), '~/books/ddia.pdf');
    await user.click(screen.getByRole('button', { name: 'settings.skills.learn.submit' }));

    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalledWith(
        expect.stringContaining('local source: ~/books/ddia.pdf; settings.skills.learn.scenarios.book.text'),
      );
    });
    expect(mockPush).toHaveBeenCalledWith('/chat-1');
  });

  it('warns when deploy scenario is chosen without active chat', async () => {
    mockGetState.mockReturnValue({
      chatId: null,
      loading: false,
      sendMessage: mockSendMessage,
    });
    const user = userEvent.setup();
    render(<SkillsLearnPanel />);

    await user.click(screen.getByRole('button', { name: 'settings.skills.learn.panelTitle' }));
    await user.click(screen.getByRole('button', { name: 'settings.skills.learn.scenarios.deploy.label' }));

    expect(mockToast.warning).toHaveBeenCalledWith('settings.skills.learn.noActiveChat');
    expect(mockSendMessage).not.toHaveBeenCalled();
  });
});
