/**
 * Side Panel approval card against the real page markup: what it shows, how it is answered, and how a pause
 * that needs no answer is told apart from one that does.
 */
import { describe, expect, it, vi } from 'vitest';
import {
  approvalEvent,
  assistantBubbles,
  bootPanel,
  browser,
  CURL_COMMAND,
  element,
  HANGS,
  installPanelHooks,
  LOOP_GUARD_PAUSE,
  overlayVisible,
  send,
  sendAndAwaitApproval,
  SHELL_ACTION,
  sse,
  textOf,
} from './sidepanelHarness';

installPanelHooks();

describe('side panel approval', () => {
  it('resumes the paused turn on approve and keeps streaming into the same message', async () => {
    const requests = await bootPanel([
      sse([{ type: 'message', data: 'Hello' }, approvalEvent()]),
      sse([{ type: 'message', data: ' world' }, { type: 'message_end' }]),
    ]);
    await sendAndAwaitApproval();

    expect(element('approval-title').textContent).toBe('approvalTitleSingle');
    expect(document.querySelector('.approval-summary')).toBeNull();
    expect(element('approval-list').textContent).not.toContain('file_write_tool');
    expect(textOf('.approval-body')).toBe('path: /a');
    expect(textOf('.approval-reason')).toBe('Write /a');
    expect(element('btn-approve').hidden).toBe(false);
    expect(element('btn-reject').textContent).toBe('approvalReject');

    element('btn-approve').click();

    await vi.waitFor(() => expect(assistantBubbles()[0].textContent).toBe('Hello world'));
    expect(requests).toHaveLength(2);
    expect(requests[1]).toMatchObject({
      message_id: requests[0].message_id,
      chat_id: requests[0].chat_id,
      query: '',
      action_mode: 'agent',
      resume_value: { decision: 'approve' },
    });
    expect(requests[1].agent_config).toEqual(requests[0].agent_config);
    expect(assistantBubbles()).toHaveLength(1);
    expect(overlayVisible()).toBe(false);
  });

  it('shows what a shell command will do and the whole command, never the internal tool name', async () => {
    await bootPanel([sse([approvalEvent({ actionRequests: [SHELL_ACTION] })])]);
    await sendAndAwaitApproval();

    expect(textOf('.approval-summary')).toBe('Download from https://api.example.com/orders');
    expect(textOf('.approval-body')).toBe(CURL_COMMAND);
    expect(textOf('.approval-reason')).toBe("Domain 'api.example.com' requires approval");
    expect(element('approval-overlay').textContent).not.toContain('bash_code_execute_tool');
    expect(element('btn-approve').hidden).toBe(false);
  });

  it('explains the command in Chinese for a Chinese browser', async () => {
    await bootPanel([sse([approvalEvent({ actionRequests: [SHELL_ACTION] })])], { uiLanguage: 'zh-CN' });
    await sendAndAwaitApproval();

    expect(textOf('.approval-summary')).toBe('从 https://api.example.com/orders 下载');
  });

  it('writes what the agent sends as text, never as markup', async () => {
    const hostile = { ...SHELL_ACTION, args: { command: '<img src=x onerror=alert(1)>' }, description: '<b>x</b>' };
    await bootPanel([sse([approvalEvent({ actionRequests: [hostile] })])]);
    await sendAndAwaitApproval();

    expect(element('approval-overlay').querySelector('img, b')).toBeNull();
    expect(textOf('.approval-body')).toBe('<img src=x onerror=alert(1)>');
  });

  it('states when an unanswered request is settled by itself', async () => {
    await bootPanel([sse([approvalEvent({ extensions: { timeout: { seconds: 120, behavior: 'deny' } } })])]);
    await sendAndAwaitApproval();

    expect(element('approval-deadline').hidden).toBe(false);
    expect(element('approval-deadline').textContent).toMatch(/^approvalDeadlineDeny:\d{2}:\d{2}:\d{2}/);
  });

  it('shows no deadline when the request carries none', async () => {
    await bootPanel([sse([approvalEvent()])]);
    await sendAndAwaitApproval();

    expect(element('approval-deadline').hidden).toBe(true);
  });

  it.each([
    ['deny', 'approvalExpiredDeny'],
    ['allow', 'approvalExpiredAllow'],
  ])('closes the card and says so once the deadline passes unanswered (default: %s)', async (behavior, notice) => {
    await bootPanel([sse([approvalEvent({ extensions: { timeout: { seconds: 0.15, behavior } } })])]);
    await send('write the file');

    await vi.waitFor(() => expect(textOf('.turn-notice')).toBe(notice), { timeout: 3000 });
    expect(overlayVisible()).toBe(false);
    expect(element('chat-input').disabled).toBe(false);
    expect(browser.notifications.clear).toHaveBeenCalledWith('approval-pending');
  });

  it('says nothing about a timeout for an approval that was answered in time', async () => {
    const requests = await bootPanel([
      sse([approvalEvent({ extensions: { timeout: { seconds: 0.6, behavior: 'deny' } } })]),
      sse([{ type: 'message_end' }]),
    ]);
    await sendAndAwaitApproval();

    element('btn-reject').click();
    await vi.waitFor(() => expect(requests).toHaveLength(2));
    await new Promise((resolveWait) => setTimeout(resolveWait, 800));

    expect(document.querySelector('.turn-notice')).toBeNull();
  });

  it('keeps the card of a newer approval open when the deadline of the one it replaced passes', async () => {
    await bootPanel([
      sse([
        approvalEvent({ extensions: { timeout: { seconds: 0.15, behavior: 'deny' } }, interruptId: 'first' }),
        approvalEvent({ actionRequests: [SHELL_ACTION], interruptId: 'second' }),
      ]),
    ]);
    await sendAndAwaitApproval();

    await new Promise((resolveWait) => setTimeout(resolveWait, 400));

    expect(overlayVisible()).toBe(true);
    expect(textOf('.approval-body')).toBe(CURL_COMMAND);
    expect(document.querySelector('.turn-notice')).toBeNull();
  });

  it('keeps the card open when the deadline is further away than a timer can wait', async () => {
    await bootPanel([sse([approvalEvent({ extensions: { timeout: { seconds: 1e9, behavior: 'deny' } } })])]);
    await sendAndAwaitApproval();

    await new Promise((resolveWait) => setTimeout(resolveWait, 100));

    expect(overlayVisible()).toBe(true);
    expect(document.querySelector('.turn-notice')).toBeNull();
  });

  it('only rejects a command too long to show in full', async () => {
    const long = { ...SHELL_ACTION, args: { command: `echo ${'a'.repeat(2500)}; rm -rf ~` } };
    const requests = await bootPanel([
      sse([approvalEvent({ actionRequests: [long] })]),
      sse([{ type: 'message_end' }]),
    ]);
    await sendAndAwaitApproval();

    expect(element('btn-approve').hidden).toBe(true);
    expect(element('approval-hint').textContent).toBe('approvalHintTooLong');
    expect(textOf('.approval-body')).not.toContain('rm -rf');

    element('btn-approve').click();
    expect(requests).toHaveLength(1);

    element('btn-reject').click();
    await vi.waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[1].resume_value).toMatchObject({ decision: 'reject' });
  });

  it('is announced as an alert dialog named by its title', async () => {
    await bootPanel([sse([approvalEvent()])]);
    const overlay = element('approval-overlay');

    expect(overlay.getAttribute('role')).toBe('alertdialog');
    expect(document.getElementById(overlay.getAttribute('aria-labelledby') ?? '')).toBe(element('approval-title'));
    expect(document.getElementById(overlay.getAttribute('aria-describedby') ?? '')).toBe(element('approval-list'));
  });

  it('puts focus on the safe answer when the user is working in the panel', async () => {
    await bootPanel([sse([approvalEvent()])]);
    vi.spyOn(document, 'hasFocus').mockReturnValue(true);

    await sendAndAwaitApproval();

    expect(document.activeElement).toBe(element('btn-reject'));
  });

  it('leaves focus alone when the user is somewhere else, so it cannot be pulled from the page they type in', async () => {
    await bootPanel([sse([approvalEvent()])]);
    vi.spyOn(document, 'hasFocus').mockReturnValue(false);

    await sendAndAwaitApproval();

    expect(document.activeElement).not.toBe(element('btn-reject'));
  });

  it('answers the interrupt its event named, and names none when the event named none', async () => {
    const addressed = await bootPanel([sse([approvalEvent({ interruptId: 'int-7' })]), sse([{ type: 'message_end' }])]);
    await sendAndAwaitApproval();
    element('btn-approve').click();
    await vi.waitFor(() => expect(addressed).toHaveLength(2));
    expect(addressed[1].resume_value).toEqual({ decision: 'approve', interruptId: 'int-7' });

    const unaddressed = await bootPanel([sse([approvalEvent()]), sse([{ type: 'message_end' }])]);
    await sendAndAwaitApproval();
    element('btn-approve').click();
    await vi.waitFor(() => expect(unaddressed).toHaveLength(2));
    expect(unaddressed[1].resume_value).toEqual({ decision: 'approve' });
  });

  it('sends a rejection with the denial reason', async () => {
    const requests = await bootPanel([sse([approvalEvent()]), sse([{ type: 'message_end' }])]);
    await sendAndAwaitApproval();

    element('btn-reject').click();

    await vi.waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[1].resume_value).toEqual({ decision: 'reject', feedback: 'User rejected this action.' });
  });

  it('shows a notice instead of an error when the approval was already settled', async () => {
    const requests = await bootPanel([
      sse([{ type: 'message', data: 'Hello' }, approvalEvent()]),
      new Response('{"detail":"This approval has already been resolved."}', { status: 409 }),
    ]);
    await sendAndAwaitApproval();

    element('btn-approve').click();

    await vi.waitFor(() => expect(textOf('.turn-notice')).toBe('approvalHandledElsewhere'));
    expect(requests).toHaveLength(2);
    expect(assistantBubbles()[0].textContent).toBe('Hello');
    expect(assistantBubbles()[0].classList.contains('error')).toBe(false);
    expect(element('btn-send').disabled).toBe(false);
  });

  it.each([
    ['the server fails', new Response('boom', { status: 500 })],
    ['the network is down', new TypeError('Failed to fetch')],
  ])('offers the answer again when %s before it was taken', async (_label, failure) => {
    const requests = await bootPanel([
      sse([{ type: 'message', data: 'Hello' }, approvalEvent()]),
      failure,
      sse([{ type: 'message', data: ' world' }, { type: 'message_end' }]),
    ]);
    await sendAndAwaitApproval();

    element('btn-approve').click();

    await vi.waitFor(() => expect(overlayVisible()).toBe(true));
    expect(textOf('.turn-notice')).toBe('approvalSendFailed');
    expect(assistantBubbles()[0].textContent).toBe('Hello');
    expect(assistantBubbles()[0].classList.contains('error')).toBe(false);
    expect(element('btn-approve').disabled).toBe(false);
    expect(element('chat-input').disabled).toBe(true);

    element('btn-approve').click();

    await vi.waitFor(() => expect(assistantBubbles()[0].textContent).toBe('Hello world'));
    expect(requests).toHaveLength(3);
    expect(requests[2]).toMatchObject({ message_id: requests[0].message_id, resume_value: { decision: 'approve' } });
    expect(overlayVisible()).toBe(false);
  });

  it('does not offer the answer again after the user cancels the resume', async () => {
    const requests = await bootPanel([sse([approvalEvent()]), HANGS]);
    await sendAndAwaitApproval();

    element('btn-approve').click();
    await vi.waitFor(() => expect(requests).toHaveLength(2));
    element('btn-cancel').click();

    await vi.waitFor(() => expect(element('btn-send').disabled).toBe(false));
    await new Promise((resolve) => setTimeout(resolve, 20)); // lets the aborted request settle before asserting what did not happen
    expect(overlayVisible()).toBe(false);
    expect(document.querySelector('.turn-notice')).toBeNull();
  });

  it('only lets an elevated request be rejected here', async () => {
    const requests = await bootPanel([
      sse([approvalEvent({ reviewConfigs: [{ irreversibleDestructive: true }] })]),
      sse([{ type: 'message_end' }]),
    ]);
    await sendAndAwaitApproval();

    expect(element('btn-approve').hidden).toBe(true);
    expect(element('approval-hint').hidden).toBe(false);
    expect(element('approval-hint').textContent).toBe('approvalHintElevated');

    element('btn-reject').click();

    await vi.waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[1].resume_value).toMatchObject({ decision: 'reject' });
  });

  it('only dismisses a request the web app has to answer', async () => {
    const requests = await bootPanel([sse([{ type: 'approval_required', data: { approval_id: 'a1' } }])]);
    await sendAndAwaitApproval();

    expect(element('btn-approve').hidden).toBe(true);
    expect(element('btn-reject').textContent).toBe('approvalDismiss');
    expect(element('approval-title').textContent).toBe('approvalTitleExternal');
    expect(element('approval-list').hidden).toBe(true);
    expect(element('approval-deadline').hidden).toBe(true);

    element('btn-reject').click();

    expect(overlayVisible()).toBe(false);
    expect(requests).toHaveLength(1);
  });

  it('says a paused step stopped instead of opening a card nobody can answer', async () => {
    const requests = await bootPanel([sse([LOOP_GUARD_PAUSE, { type: 'message_end' }])], { windowFocused: false });

    await send('read the file');

    await vi.waitFor(() => expect(textOf('.turn-notice')).toBe('panelToolStuckPaused'));
    await vi.waitFor(() => expect(element('chat-input').disabled).toBe(false));
    await new Promise((resolve) => setTimeout(resolve, 20)); // lets the reminder decision settle before asserting what did not happen
    expect(overlayVisible()).toBe(false);
    expect(element('chat-input').placeholder).toBe('panelInputPlaceholder');
    expect(browser.notifications.create).not.toHaveBeenCalled();
    expect(JSON.stringify(document.body.innerHTML)).not.toMatch(/tool_stuck|bash_code_execute_tool|call-1/);
    expect(requests).toHaveLength(1);
  });

  it('says it once when parallel tool calls stop together', async () => {
    const second = {
      ...LOOP_GUARD_PAUSE,
      data: { ...LOOP_GUARD_PAUSE.data, tool_name: 'file_read_tool', tool_call_id: 'call-2' },
      interruptId: 'interrupt-2.0',
    };
    await bootPanel([sse([LOOP_GUARD_PAUSE, second, { type: 'message_end' }])]);

    await send('read the files');

    await vi.waitFor(() => expect(document.querySelectorAll('.turn-notice')).toHaveLength(1));
    await new Promise((resolve) => setTimeout(resolve, 20)); // lets the rest of the stream arrive before counting again
    expect(document.querySelectorAll('.turn-notice')).toHaveLength(1);
    expect(overlayVisible()).toBe(false);
  });

  it('drops the pending approval when the chat is reset', async () => {
    const requests = await bootPanel([sse([approvalEvent()])]);
    await sendAndAwaitApproval();

    element('btn-new-chat').click();
    element('btn-approve').click();

    expect(overlayVisible()).toBe(false);
    expect(requests).toHaveLength(1);
    expect(element('chat-input').disabled).toBe(false);
  });
});
