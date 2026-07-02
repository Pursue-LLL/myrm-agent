import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockSendMessage = vi.fn();
const mockGetState = vi.fn();
const mockToast = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
}));

vi.mock('sonner', () => ({ toast: mockToast }));

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => mockGetState(),
  },
}));

vi.mock('@/components/primitives/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <div data-testid="tooltip">{children}</div>,
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import ExtractToSkillButton from '../ExtractToSkillButton';
import type { Message } from '@/store/chat/types';

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    messageId: 'msg-1',
    role: 'assistant',
    content: 'This is a useful coding pattern for error handling.',
    createdAt: '2026-07-01T00:00:00Z',
    ...overrides,
  } as Message;
}

describe('ExtractToSkillButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetState.mockReturnValue({
      loading: false,
      sendMessage: mockSendMessage,
    });
    mockSendMessage.mockResolvedValue(undefined);
  });

  it('renders nothing for empty message content', () => {
    const { container } = render(<ExtractToSkillButton message={makeMessage({ content: '' })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing for whitespace-only content', () => {
    const { container } = render(<ExtractToSkillButton message={makeMessage({ content: '   ' })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders a button with aria-label for non-empty messages', () => {
    render(<ExtractToSkillButton message={makeMessage()} />);
    expect(screen.getByRole('button', { name: 'extractToSkill.title' })).toBeInTheDocument();
  });

  it('sends /learn command with message content on click', async () => {
    const user = userEvent.setup();
    render(<ExtractToSkillButton message={makeMessage()} />);

    await user.click(screen.getByRole('button'));
    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalledTimes(1);
    });

    const sentArg = mockSendMessage.mock.calls[0][0] as string;
    expect(sentArg).toContain('/learn');
    expect(sentArg).toContain('This is a useful coding pattern for error handling.');
    expect(mockToast.success).toHaveBeenCalledWith('extractToSkill.success');
  });

  it('shows warning toast when Agent is busy (loading=true)', async () => {
    mockGetState.mockReturnValue({ loading: true, sendMessage: mockSendMessage });
    const user = userEvent.setup();
    render(<ExtractToSkillButton message={makeMessage()} />);

    await user.click(screen.getByRole('button'));
    expect(mockSendMessage).not.toHaveBeenCalled();
    expect(mockToast.warning).toHaveBeenCalledWith('extractToSkill.busy');
  });

  it('disables button after successful send', async () => {
    const user = userEvent.setup();
    render(<ExtractToSkillButton message={makeMessage()} />);

    await user.click(screen.getByRole('button'));
    await waitFor(() => {
      expect(screen.getByRole('button')).toBeDisabled();
    });
  });

  it('resets to idle on sendMessage error', async () => {
    mockSendMessage.mockRejectedValue(new Error('Network error'));
    const user = userEvent.setup();
    render(<ExtractToSkillButton message={makeMessage()} />);

    await user.click(screen.getByRole('button'));
    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('extractToSkill.error');
    });
    expect(screen.getByRole('button')).not.toBeDisabled();
  });

  it('prevents double-click sending', async () => {
    let resolve: () => void;
    mockSendMessage.mockImplementation(() => new Promise<void>((r) => { resolve = r; }));
    const user = userEvent.setup();
    render(<ExtractToSkillButton message={makeMessage()} />);

    await user.click(screen.getByRole('button'));
    await user.click(screen.getByRole('button'));

    resolve!();
    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalledTimes(1);
    });
  });

  it('includes i18n learnContext prefix in sent message', async () => {
    const user = userEvent.setup();
    render(<ExtractToSkillButton message={makeMessage()} />);

    await user.click(screen.getByRole('button'));
    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalledTimes(1);
    });

    const sentArg = mockSendMessage.mock.calls[0][0] as string;
    expect(sentArg).toMatch(/^\/learn extractToSkill\.learnContext/);
  });

  it('handles very long message content', async () => {
    const longContent = 'x'.repeat(10000);
    const user = userEvent.setup();
    render(<ExtractToSkillButton message={makeMessage({ content: longContent })} />);

    await user.click(screen.getByRole('button'));
    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalledTimes(1);
    });

    const sentArg = mockSendMessage.mock.calls[0][0] as string;
    expect(sentArg).toContain(longContent);
    expect(mockToast.success).toHaveBeenCalled();
  });

  it('handles message with special characters and newlines', async () => {
    const specialContent = 'Line1\nLine2\n```code```\n<div>html</div>';
    const user = userEvent.setup();
    render(<ExtractToSkillButton message={makeMessage({ content: specialContent })} />);

    await user.click(screen.getByRole('button'));
    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalledTimes(1);
    });

    const sentArg = mockSendMessage.mock.calls[0][0] as string;
    expect(sentArg).toContain(specialContent);
  });

  it('shows loading spinner during sending state', async () => {
    let resolve: () => void;
    mockSendMessage.mockImplementation(() => new Promise<void>((r) => { resolve = r; }));
    const user = userEvent.setup();
    const { container } = render(<ExtractToSkillButton message={makeMessage()} />);

    await user.click(screen.getByRole('button'));
    const spinner = container.querySelector('.animate-spin');
    expect(spinner).toBeInTheDocument();

    resolve!();
    await waitFor(() => {
      expect(mockToast.success).toHaveBeenCalled();
    });
  });

  it('shows sent tooltip text after successful send', async () => {
    const user = userEvent.setup();
    render(<ExtractToSkillButton message={makeMessage()} />);

    await user.click(screen.getByRole('button'));
    await waitFor(() => {
      expect(screen.getByText('extractToSkill.sent')).toBeInTheDocument();
    });
  });

  it('does not call sendMessage when button is disabled (sent state)', async () => {
    const user = userEvent.setup();
    render(<ExtractToSkillButton message={makeMessage()} />);

    await user.click(screen.getByRole('button'));
    await waitFor(() => expect(mockSendMessage).toHaveBeenCalledTimes(1));

    mockSendMessage.mockClear();
    await user.click(screen.getByRole('button'));
    expect(mockSendMessage).not.toHaveBeenCalled();
  });
});
