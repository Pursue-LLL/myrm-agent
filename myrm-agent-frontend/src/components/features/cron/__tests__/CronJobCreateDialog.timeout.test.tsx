// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { jsonResponse } from '@/test-utils/riskHeld';

const { agentState, providerState, chatState } = vi.hoisted(() => ({
  agentState: { agents: [] as never[], fetchAgents: vi.fn() },
  providerState: { defaultModelConfig: { baseModel: { primary: null } } },
  chatState: { chatHistoryItems: [] as never[] },
}));

vi.mock('sonner', () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));
vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: vi.fn(async () => true),
  markLocalBackendUnreachable: vi.fn(),
}));
vi.mock('@/store/useAgentStore', () => ({ default: () => agentState }));
vi.mock('@/store/useProviderStore', () => ({ default: () => providerState }));
vi.mock('@/store/useChatStore', () => ({
  default: (select: (state: typeof chatState) => unknown) => select(chatState),
}));
vi.mock('@/services/channels', () => ({ listChannelStatuses: vi.fn(async () => []) }));
vi.mock('@/services/workflowTemplates', () => ({ fetchWorkflowTemplates: vi.fn(async () => ({ templates: [] })) }));
vi.mock('@/services/cron', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/cron')>()),
  checkCronPrerequisite: vi.fn(async () => {
    throw new Error('no prerequisite data');
  }),
}));

import CronJobCreateDialog from '../CronJobCreateDialog';

const posts: Array<Record<string, unknown>> = [];

function stubCronApi(): void {
  posts.length = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      if (String(url).endsWith('/health/info')) {
        return jsonResponse(200, { deploy_mode: 'local' });
      }
      if (init?.method === 'POST') {
        posts.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        return jsonResponse(500, { detail: 'stop after capturing the request' });
      }
      return jsonResponse(200, {});
    }),
  );
}

function openCustomJobForm(): void {
  render(<CronJobCreateDialog open onOpenChange={vi.fn()} />);
  fireEvent.click(screen.getByTestId('cron-create-mode-custom'));
  fireEvent.change(screen.getByPlaceholderText('createPromptPlaceholder'), { target: { value: 'Summarise the news' } });
  fireEvent.change(screen.getByPlaceholderText('createCronPlaceholder'), { target: { value: '0 9 * * *' } });
}

const timeoutInput = (): HTMLElement => screen.getByRole('spinbutton', { name: 'timeoutLabel' });
const submitButton = (): HTMLElement => screen.getByRole('button', { name: 'createSubmit' });

describe('the run time limit in the create dialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    stubCronApi();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends the limit the user typed', async () => {
    openCustomJobForm();
    fireEvent.change(timeoutInput(), { target: { value: '900' } });
    fireEvent.click(submitButton());

    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]?.timeout_seconds).toBe(900);
  });

  it('leaves the limit to the server default when the field is empty', async () => {
    openCustomJobForm();
    fireEvent.click(submitButton());

    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).not.toHaveProperty('timeout_seconds');
  });

  it('drops a limit typed for another job type once the job becomes a reminder', async () => {
    openCustomJobForm();
    fireEvent.change(timeoutInput(), { target: { value: '900' } });
    fireEvent.click(screen.getByRole('radio', { name: 'jobTypeReminder' }));
    fireEvent.click(submitButton());

    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).not.toHaveProperty('timeout_seconds');
  });

  it.each(['5', '3601', '1.5', '-30'])('refuses to create the job with the limit %s', (typed) => {
    openCustomJobForm();
    fireEvent.change(timeoutInput(), { target: { value: typed } });

    expect((submitButton() as HTMLButtonElement).disabled).toBe(true);
    expect(timeoutInput().getAttribute('aria-invalid')).toBe('true');
    expect(posts).toHaveLength(0);
  });

  it('has no limit to set for a reminder, which is delivered at once', () => {
    openCustomJobForm();
    fireEvent.click(screen.getByRole('radio', { name: 'jobTypeReminder' }));

    expect(screen.queryByRole('spinbutton', { name: 'timeoutLabel' })).toBeNull();
  });
});
