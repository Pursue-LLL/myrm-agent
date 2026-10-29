/**
 * Side Panel controller against the real page markup while an approval waits: the input stays closed until the approval
 * is answered, and a system notification is raised when the window is not in front and withdrawn once it is answered.
 */
import { describe, expect, it, vi } from 'vitest';
import {
  approvalEvent,
  bootPanel,
  browser,
  element,
  installPanelHooks,
  overlayVisible,
  send,
  sendAndAwaitApproval,
  SHELL_ACTION,
  sse,
} from './sidepanelHarness';

installPanelHooks();

describe('side panel input while an approval waits', () => {
  it('closes the input until the approval is answered, so a new message cannot overtake it', async () => {
    const requests = await bootPanel([sse([approvalEvent()]), sse([{ type: 'message_end' }])]);
    await sendAndAwaitApproval();

    expect(element('chat-input').disabled).toBe(true);
    expect(element('btn-send').disabled).toBe(true);
    expect(element('chat-input').placeholder).toBe('panelInputPaused');

    element('chat-input').value = 'sneaky';
    element('chat-input').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    element('btn-send').click();
    expect(requests).toHaveLength(1);
    expect(document.querySelectorAll('.message.user')).toHaveLength(1);
    expect(overlayVisible()).toBe(true);

    element('btn-reject').click();

    await vi.waitFor(() => expect(requests).toHaveLength(2));
    await vi.waitFor(() => expect(element('chat-input').disabled).toBe(false));
    expect(element('btn-send').disabled).toBe(false);
    expect(element('chat-input').placeholder).toBe('panelInputPlaceholder');
  });

  it('opens the input again when a request only the web app can answer is dismissed', async () => {
    await bootPanel([sse([{ type: 'approval_required', data: { approval_id: 'a1' } }])]);
    await sendAndAwaitApproval();
    expect(element('chat-input').disabled).toBe(true);

    element('btn-reject').click();

    expect(element('chat-input').disabled).toBe(false);
  });
});

describe('side panel approval reminder', () => {
  it('raises a system notification without the command when the browser window is not in front', async () => {
    await bootPanel([sse([approvalEvent({ actionRequests: [SHELL_ACTION] })])], { windowFocused: false });

    await sendAndAwaitApproval();

    await vi.waitFor(() => expect(browser.notifications.create).toHaveBeenCalledTimes(1));
    const [id, options] = browser.notifications.create.mock.calls[0];
    expect(id).toBe('approval-pending');
    expect(options.title).toBe('notifyApprovalTitle');
    expect(JSON.stringify(options)).not.toContain('curl');
    expect(JSON.stringify(options)).not.toContain('bash_code_execute_tool');
  });

  it('stays quiet while the user is looking at the browser', async () => {
    await bootPanel([sse([approvalEvent()])], { windowFocused: true });

    await sendAndAwaitApproval();
    await new Promise((resolve) => setTimeout(resolve, 20)); // lets the reminder decision settle before asserting what did not happen

    expect(browser.notifications.create).not.toHaveBeenCalled();
  });

  it('withdraws the notification when the approval is answered', async () => {
    await bootPanel([sse([approvalEvent()]), sse([{ type: 'message_end' }])], { windowFocused: false });
    await sendAndAwaitApproval();

    element('btn-reject').click();

    expect(browser.notifications.clear).toHaveBeenCalledWith('approval-pending');
  });
});
