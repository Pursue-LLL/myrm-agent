// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { installEnglishToastTranslator, jsonResponse, riskHeldRefusalBody, riskHeldTitle } from '@/test-utils/riskHeld';

const toastMock = vi.hoisted(() =>
  Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
);

vi.mock('@/lib/utils/toast', () => ({ toast: toastMock }));
vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: vi.fn(async () => true),
  markLocalBackendUnreachable: vi.fn(),
}));
const stableT = (key: string) => key;
vi.mock('next-intl', () => ({ useTranslations: () => stableT }));

import SessionAdvisorPanel from '../SessionAdvisorPanel';

const HELD_QUESTION = 'use key sk-AAAAAABBBBBBCCCCCCDDDD-0';

/** The message list loads normally; the ask gets `askReply`. */
function stubAdvisorApi(askReply: () => Response): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: RequestInfo | URL) =>
      String(url).endsWith('/advisor/ask') ? askReply() : jsonResponse(200, { data: { messages: [] } }),
    ),
  );
}

async function ask(question: string): Promise<HTMLTextAreaElement> {
  render(<SessionAdvisorPanel chatId="chat-1" open onOpenChange={vi.fn()} />);
  const input = (await screen.findByTestId('copilot-advisor-input')) as HTMLTextAreaElement;
  fireEvent.change(input, { target: { value: question } });
  fireEvent.click(screen.getByTestId('copilot-advisor-send'));
  return input;
}

describe('the session advisor panel when the server holds a question', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installEnglishToastTranslator();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('explains it once and gives the question back in the box instead of eating it', async () => {
    stubAdvisorApi(() => jsonResponse(400, riskHeldRefusalBody));

    const input = await ask(HELD_QUESTION);

    await waitFor(() => expect(toastMock.error).toHaveBeenCalledTimes(1));
    expect(toastMock.error.mock.calls[0]?.[0]).toBe(riskHeldTitle);
    await waitFor(() => expect(input.value).toBe(HELD_QUESTION));
  });

  it('empties the box once the question is answered', async () => {
    stubAdvisorApi(() =>
      jsonResponse(200, {
        data: {
          reply: 'Try the second option.',
          tier: 'tier0',
          message: { id: 'm1', role: 'assistant', content: 'Try the second option.', tier: 'tier0', created_at: '' },
        },
      }),
    );

    const input = await ask('what next?');

    await waitFor(() => expect(screen.getByTestId('copilot-advisor-send').textContent).toBe('advisorSend'));
    expect(input.value).toBe('');
    expect(toastMock.error).not.toHaveBeenCalled();
  });
});
