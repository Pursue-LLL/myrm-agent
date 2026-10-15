// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import en from '../../../../../../locales/en.json';
import type { TreeNode } from '@/lib/utils/subagent/subagentTree';

const toasts = vi.hoisted(() => ({
  sonner: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
  held: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));
const fetchMock = vi.hoisted(() => vi.fn());

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('sonner', () => ({ toast: toasts.sonner }));
vi.mock('@/lib/utils/toast', () => ({ toast: toasts.held }));
vi.mock('@/lib/api', () => ({ fetchWithTimeout: fetchMock }));

import { setGlobalTranslator } from '@/services/i18nToastService';
import { SubagentTreeNode } from '../SubagentTree';

const node: TreeNode = {
  task_id: 'task-1',
  parent_task_id: '',
  agent_type: 'researcher',
  description: 'Investigate documentation',
  status: 'running',
  progress: 30,
  stream: [],
  children: [],
};

const refusal = {
  detail: {
    code: 'risk_held',
    message: 'Text held by a risk rule',
    rules: [{ rule_id: 'api_key_like', display_name: 'API key or cloud credential pattern', severity: 'critical' }],
  },
};

function respond(ok: boolean, status: number, body: unknown) {
  fetchMock.mockResolvedValue({ ok, status, json: () => Promise.resolve(body) });
}

async function sendSteer(text: string) {
  render(<SubagentTreeNode node={node} chatId="chat-1" setOpen={vi.fn()} />);
  fireEvent.click(screen.getByTitle('steerTitle'));
  const input = screen.getByPlaceholderText('steerPlaceholder') as HTMLInputElement;
  fireEvent.change(input, { target: { value: text } });
  fireEvent.click(screen.getByText('send'));
  return input;
}

describe('SubagentTreeNode steer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    const messages = en as Record<string, unknown>;
    const lookup = (key: string) =>
      key
        .split('.')
        .reduce<unknown>((cursor, part) => (cursor as Record<string, unknown> | undefined)?.[part], messages);
    setGlobalTranslator(
      Object.assign(
        (key: string, values?: Record<string, unknown>) =>
          String(lookup(key) ?? key).replace(/\{(\w+)\}/g, (_, name: string) => String(values?.[name] ?? '')),
        { has: (key: string) => typeof lookup(key) === 'string' },
      ),
    );
  });

  it('names the rule that held the message instead of a generic failure, and keeps the text for editing', async () => {
    respond(false, 400, refusal);

    const input = await sendSteer('use the key sk-AAAAAABBBBBBCCCCCCDDDD');

    await waitFor(() => expect(toasts.held.error).toHaveBeenCalledTimes(1));
    const [title, options] = toasts.held.error.mock.calls[0] as [string, { description: string }];
    expect(title).toBe(en.settings.securityPolicy.riskRules.blockedTitle);
    expect(options.description).toContain('Matched: ');
    expect(toasts.sonner.error).not.toHaveBeenCalled();
    expect(input.value).toBe('use the key sk-AAAAAABBBBBBCCCCCCDDDD');
  });

  it('reports any other failure with the server message', async () => {
    respond(false, 404, { message: 'Subagent task-1 is not running or not found in memory.' });

    await sendSteer('only the 2026 rows');

    await waitFor(() =>
      expect(toasts.sonner.error).toHaveBeenCalledWith('Subagent task-1 is not running or not found in memory.'),
    );
    expect(toasts.held.error).not.toHaveBeenCalled();
  });

  it('clears the input and confirms when the subagent accepts the message', async () => {
    respond(true, 200, { success: true });

    const input = await sendSteer('only the 2026 rows');

    await waitFor(() => expect(toasts.sonner.success).toHaveBeenCalledWith('steerSuccess'));
    expect(fetchMock).toHaveBeenCalledWith(
      '/chats/chat-1/subagents/task-1/steer',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(input.isConnected).toBe(false);
  });
});
