// @vitest-environment jsdom
import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ADVISOR_QUESTION_MAX_LENGTH } from '@/lib/constants/advisor-question';
import { deferred } from '@/test-utils/deferred';
import { jsonResponse } from '@/test-utils/riskHeld';

vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: vi.fn(async () => true),
  markLocalBackendUnreachable: vi.fn(),
}));
const stableT = (key: string) => key;
vi.mock('next-intl', () => ({ useTranslations: () => stableT }));

import SessionAdvisorPanel from '../SessionAdvisorPanel';

// A rare han character is one character to the server and two UTF-16 units to the browser.
const CHARACTER = '\u{20BB7}';

const earlierQuestion = { id: 'm1', role: 'user', content: 'what did you change?', tier: '', created_at: '' };

/** The thread holds `thread`; every ask is answered, and its question is pushed onto the returned list. */
function stubAdvisorApi(thread: unknown[] = []): string[] {
  const askedQuestions: string[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      if (String(url).endsWith('/advisor/ask')) {
        askedQuestions.push((JSON.parse(String(init?.body)) as { question: string }).question);
        return jsonResponse(200, {
          data: {
            reply: 'ok',
            tier: 'tier0',
            message: { id: 'm2', role: 'assistant', content: 'ok', tier: 'tier0', created_at: '' },
          },
        });
      }
      return jsonResponse(200, { data: { messages: thread } });
    }),
  );
  return askedQuestions;
}

describe('the session advisor panel', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('stops the input at the length the server accepts', async () => {
    stubAdvisorApi();
    render(<SessionAdvisorPanel chatId="chat-1" open onOpenChange={vi.fn()} />);

    const input = (await screen.findByTestId('copilot-advisor-input')) as HTMLTextAreaElement;

    expect(input.maxLength).toBe(ADVISOR_QUESTION_MAX_LENGTH);
  });

  it('cuts a question a command handed over to the length the server accepts, which no input box could stop', async () => {
    const asked = stubAdvisorApi();
    render(
      <SessionAdvisorPanel
        chatId="chat-1"
        open
        onOpenChange={vi.fn()}
        initialQuestion={CHARACTER.repeat(ADVISOR_QUESTION_MAX_LENGTH + 10)}
      />,
    );

    await waitFor(() => expect(asked).toHaveLength(1));

    expect(asked[0]).toBe(CHARACTER.repeat(ADVISOR_QUESTION_MAX_LENGTH));
  });

  it('shows the thread once it opens', async () => {
    stubAdvisorApi([earlierQuestion]);
    render(<SessionAdvisorPanel chatId="chat-1" open onOpenChange={vi.fn()} />);

    expect(await screen.findByText(earlierQuestion.content)).toBeTruthy();
  });

  it('drops a thread that arrives after the panel moved to another chat', async () => {
    const slowThread = deferred<Response>();
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: RequestInfo | URL) =>
        String(url).includes('/chat-1/')
          ? slowThread.promise
          : jsonResponse(200, { data: { messages: [{ ...earlierQuestion, id: 'm3', content: 'the other chat' }] } }),
      ),
    );
    const { rerender } = render(<SessionAdvisorPanel chatId="chat-1" open onOpenChange={vi.fn()} />);
    rerender(<SessionAdvisorPanel chatId="chat-2" open onOpenChange={vi.fn()} />);
    await screen.findByText('the other chat');

    await act(async () => {
      slowThread.resolve(jsonResponse(200, { data: { messages: [earlierQuestion] } }));
    });

    expect(screen.queryByText(earlierQuestion.content)).toBeNull();
    expect(screen.getByText('the other chat')).toBeTruthy();
  });
});
