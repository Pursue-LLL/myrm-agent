// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { installEnglishToastTranslator, jsonResponse, riskHeldRefusalBody, riskHeldTitle } from '@/test-utils/riskHeld';

const { sonnerToast, riskToast, agentState, providerState, chatState } = vi.hoisted(() => ({
  sonnerToast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
  riskToast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
  agentState: { agents: [] as never[], fetchAgents: vi.fn() },
  providerState: { defaultModelConfig: { baseModel: { primary: null } } },
  chatState: { chatHistoryItems: [] as never[] },
}));

vi.mock('sonner', () => ({ toast: sonnerToast }));
vi.mock('@/lib/utils/toast', () => ({ toast: riskToast }));
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

/** Fills a custom daily job and presses create; `/health/info` and everything else but the create request succeed. */
async function createCustomJob(): Promise<void> {
  render(<CronJobCreateDialog open onOpenChange={vi.fn()} />);
  fireEvent.click(screen.getByTestId('cron-create-mode-custom'));
  fireEvent.change(screen.getByPlaceholderText('createPromptPlaceholder'), {
    target: { value: 'Deploy with key sk-AAAAAABBBBBBCCCCCCDDDD-0' },
  });
  fireEvent.change(screen.getByPlaceholderText('createCronPlaceholder'), { target: { value: '0 9 * * *' } });
  fireEvent.click(screen.getByRole('button', { name: 'createSubmit' }));
}

function stubCronApi(createReply: () => Response): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: RequestInfo | URL, init?: RequestInit) =>
      String(url).endsWith('/health/info')
        ? jsonResponse(200, { deploy_mode: 'local' })
        : init?.method === 'POST'
          ? createReply()
          : jsonResponse(200, {}),
    ),
  );
}

describe('creating a custom scheduled job whose prompt the server holds', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installEnglishToastTranslator();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('explains the held prompt once, shows no failure toast of its own and keeps the form', async () => {
    stubCronApi(() => jsonResponse(400, riskHeldRefusalBody));

    await createCustomJob();

    await waitFor(() => expect(riskToast.error).toHaveBeenCalledTimes(1));
    expect(riskToast.error.mock.calls[0]?.[0]).toBe(riskHeldTitle);
    expect(sonnerToast.error).not.toHaveBeenCalled();
    expect(screen.getByDisplayValue('Deploy with key sk-AAAAAABBBBBBCCCCCCDDDD-0')).toBeDefined();
  });

  it('still reports any other failure with its own toast', async () => {
    stubCronApi(() => jsonResponse(500, { detail: 'Scheduler is down' }));

    await createCustomJob();

    await waitFor(() => expect(sonnerToast.error).toHaveBeenCalledWith('actionFail'));
  });
});
