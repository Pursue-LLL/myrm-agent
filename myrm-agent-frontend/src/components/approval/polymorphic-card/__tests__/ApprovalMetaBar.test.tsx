import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApprovalMetaBar } from '../ApprovalMetaBar';

const mocks = vi.hoisted(() => ({ push: vi.fn(), hideDrawer: vi.fn() }));

vi.mock('next-intl', async () => (await import('./approvalStubs')).nextIntlModule);
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock('@/store/useApprovalStore', () => ({
  default: (select: (state: { hideDrawer: () => void }) => unknown) => select({ hideDrawer: mocks.hideDrawer }),
}));

const IN_TEN_MINUTES = new Date(Date.now() + 10 * 60_000).toISOString();
const COUNTDOWN = '[aria-live="polite"]';
const JUMP_BUTTON = 'notifications.jumpToChatAria';

describe('ApprovalMetaBar', () => {
  beforeEach(() => {
    mocks.push.mockClear();
    mocks.hideDrawer.mockClear();
  });

  afterEach(cleanup);

  it('renders nothing when the approval has neither a chat nor an expiry', () => {
    const { container } = render(<ApprovalMetaBar />);

    expect(container.firstChild).toBeNull();
  });

  it('offers the way back to the chat, without a countdown, when there is no expiry', () => {
    const { container } = render(<ApprovalMetaBar chatId="chat-9" />);

    expect(screen.getByRole('button', { name: JUMP_BUTTON }).textContent).toBe('notifications.jumpToChat');
    expect(container.querySelector(COUNTDOWN)).toBeNull();
  });

  it('runs no countdown clock when there is no expiry', () => {
    const setIntervalSpy = vi.spyOn(window, 'setInterval');

    render(<ApprovalMetaBar chatId="chat-9" />);

    expect(setIntervalSpy).not.toHaveBeenCalled();
    setIntervalSpy.mockRestore();
  });

  it('closes the drawer and opens the chat when the way back is pressed', () => {
    render(<ApprovalMetaBar chatId="chat-9" expiresAt={IN_TEN_MINUTES} />);

    fireEvent.click(screen.getByRole('button', { name: JUMP_BUTTON }));

    expect(mocks.hideDrawer).toHaveBeenCalledTimes(1);
    expect(mocks.push).toHaveBeenCalledExactlyOnceWith('/chat/chat-9');
    expect(mocks.hideDrawer.mock.invocationCallOrder[0]).toBeLessThan(mocks.push.mock.invocationCallOrder[0]);
  });

  it('shows the countdown, without the way back, when there is no chat', () => {
    const { container } = render(<ApprovalMetaBar expiresAt={IN_TEN_MINUTES} />);

    expect(screen.queryByRole('button')).toBeNull();
    expect(container.querySelector(COUNTDOWN)?.textContent).toMatch(/^\d+:\d{2}$/);
  });
});
