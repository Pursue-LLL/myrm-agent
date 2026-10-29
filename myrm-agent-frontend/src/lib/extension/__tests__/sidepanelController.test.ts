/**
 * Side Panel controller against the real page markup: the stream (tool rows, errors, a refusal because the agent is busy,
 * the language of the page) and the page context sent along with a message.
 */
import { describe, expect, it, vi } from 'vitest';
import {
  assistantBubbles,
  bootPanel,
  browser,
  element,
  installPanelHooks,
  send,
  sse,
  textOf,
} from './sidepanelHarness';

installPanelHooks();

describe('side panel stream', () => {
  it('renders each tool call as a row in the assistant message and settles it', async () => {
    await bootPanel([
      sse([
        { type: 'tool_start', tool_name: 'file_read_tool' },
        { type: 'tool_end', tool_name: 'file_read_tool' },
        { type: 'tool_start', tool_name: 'bash_code_execute_tool' },
        { type: 'tool_failure', tool_name: 'bash_code_execute_tool' },
        { type: 'message', data: 'Done' },
        { type: 'message_end' },
      ]),
    ]);

    await send('read it');

    await vi.waitFor(() => expect(assistantBubbles()[0].textContent).toBe('Done'));
    const steps = [...document.querySelectorAll('.message.assistant .tool-step')];
    expect(steps.map((step) => step.className)).toEqual(['tool-step done', 'tool-step error']);
    expect(steps.map((step) => step.querySelector('.name')?.textContent)).toEqual([
      'file_read_tool',
      'bash_code_execute_tool',
    ]);
  });

  it('says which tool is running in the language of the UI, and goes back to thinking', async () => {
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    const open = new ReadableStream<Uint8Array>({ start: (c) => void (controller = c) });
    const push = (event: object) => controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(event)}\n`));
    await bootPanel([new Response(open, { status: 200 })]);

    await send('read it');
    push({ type: 'tool_start', tool_name: 'file_read_tool' });
    await vi.waitFor(() => expect(element('streaming-label').textContent).toBe('panelUsingTool:file_read_tool'));

    push({ type: 'tool_end', tool_name: 'file_read_tool' });
    await vi.waitFor(() => expect(element('streaming-label').textContent).toBe('panelThinking'));

    push({ type: 'message_end' });
    controller.close();
    await vi.waitFor(() => expect(element('btn-send').disabled).toBe(false));
  });

  it('tells the user something went wrong without showing the server error text', async () => {
    await bootPanel([new Response('Traceback: db password=hunter2', { status: 500 })]);

    await send('hi');

    await vi.waitFor(() => expect(assistantBubbles()[0].textContent).toBe('panelStreamError'));
    expect(assistantBubbles()[0].classList.contains('error')).toBe(true);
    expect(console.error).toHaveBeenCalled();
    expect(document.body.textContent).not.toContain('hunter2');
  });

  it('keeps the streamed text and appends the same plain message when the stream reports an error', async () => {
    await bootPanel([
      sse([
        { type: 'message', data: 'Partial' },
        { type: 'error', error: 'RuntimeError: provider quota exceeded (key sk-123)' },
      ]),
    ]);

    await send('hi');

    await vi.waitFor(() => expect(assistantBubbles()[0].textContent).toBe('Partial\n\npanelStreamError'));
    expect(assistantBubbles()[0].classList.contains('error')).toBe(true);
    expect(document.body.textContent).not.toContain('sk-123');
  });

  it('says the agent is still busy, not that the connection failed, when the server refuses a message for that reason', async () => {
    await bootPanel([
      sse([
        {
          type: 'error',
          error_type: 'AgentBusyError',
          data: 'Agent is busy processing another request for this session.',
          status_code: 409,
        },
      ]),
    ]);

    await send('and then?');

    await vi.waitFor(() => expect(assistantBubbles()[0].textContent).toBe('panelAgentBusy'));
    expect(assistantBubbles()[0].classList.contains('error')).toBe(true);
    expect(document.body.textContent).not.toContain('Agent is busy processing');
    await vi.waitFor(() => expect(element('btn-send').disabled).toBe(false));
  });

  it('marks the refusal of a message for a reason the browser never sees as an error', async () => {
    await bootPanel([
      sse([{ type: 'error', error_type: 'AgentBusyError', data: 'Agent is busy processing another request.' }]),
    ]);

    await send('and then?');

    await vi.waitFor(() => expect(assistantBubbles()[0].textContent).toBe('panelAgentBusy'));
    expect(assistantBubbles()[0].classList.contains('error')).toBe(true);
  });

  it('recognizes the refusal by its status code when the payload carries no error type', async () => {
    await bootPanel([sse([{ type: 'error', status_code: 409, data: 'Agent is busy processing another request.' }])]);

    await send('and then?');

    await vi.waitFor(() => expect(assistantBubbles()[0].textContent).toBe('panelAgentBusy'));
  });
  it('puts the page in the language of the browser', async () => {
    await bootPanel([], { uiLanguage: 'zh-CN' });

    expect(document.documentElement.lang).toBe('zh-CN');
    expect(element('empty-state').querySelector('.title')?.textContent).toBe('panelEmptyTitle');
    expect(element('btn-new-chat').title).toBe('panelNewChat');
    expect(element('btn-cancel').title).toBe('panelCancel');
    expect(element('chat-input').placeholder).toBe('panelInputPlaceholder');
    expect(element('not-connected').textContent).toContain('panelNotConnected');
  });
});

describe('side panel page context', () => {
  const tab = { id: 4, title: 'Docs', url: 'https://example.com/a' };

  it('puts the page the user is on in front of the message', async () => {
    const requests = await bootPanel([sse([{ type: 'message_end' }])], { activeTab: tab });
    expect(textOf('#context-value')).toBe('Docs');
    expect(element('context-bar').classList.contains('visible')).toBe(true);

    await send('summarize');

    await vi.waitFor(() => expect(requests).toHaveLength(1));
    expect(requests[0].query).toBe('[Current page: Docs — https://example.com/a]\n\nsummarize');
  });

  it('leaves the page out once the user dismisses it', async () => {
    const requests = await bootPanel([sse([{ type: 'message_end' }])], { activeTab: tab });

    element('context-dismiss').click();
    await send('summarize');

    await vi.waitFor(() => expect(requests).toHaveLength(1));
    expect(requests[0].query).toBe('summarize');
    expect(element('context-bar').classList.contains('visible')).toBe(false);
  });

  it('ignores browser-internal pages', async () => {
    const requests = await bootPanel([sse([{ type: 'message_end' }])], {
      activeTab: { id: 1, title: 'Settings', url: 'chrome://settings' },
    });

    await send('hi');

    await vi.waitFor(() => expect(requests).toHaveLength(1));
    expect(requests[0].query).toBe('hi');
  });

  it('quotes the selected text in the message, once', async () => {
    const requests = await bootPanel([sse([{ type: 'message_end' }]), sse([{ type: 'message_end' }])]);
    browser.messageListeners.forEach((listener) => listener({ type: 'selected_text', text: '  a quote  ' }));
    expect(textOf('#selection-text')).toBe('a quote');
    expect(element('selection-ctx').classList.contains('visible')).toBe(true);

    await send('explain');
    await vi.waitFor(() => expect(element('btn-send').disabled).toBe(false));
    await send('and again');

    await vi.waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[0].query).toBe('[Selected text: "a quote"]\n\nexplain');
    expect(requests[1].query).toBe('and again');
    expect(element('selection-ctx').classList.contains('visible')).toBe(false);
  });

  it('takes the question of a context-menu ask along with its selection', async () => {
    await bootPanel([]);

    browser.messageListeners.forEach((listener) =>
      listener({ type: 'context_menu_query', text: 'selected', prompt: 'What is this?' }),
    );

    expect(element('chat-input').value).toBe('What is this?');
    expect(textOf('#selection-text')).toBe('selected');
  });
});
