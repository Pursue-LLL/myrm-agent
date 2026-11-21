import { afterEach, describe, expect, it, vi } from 'vitest';

import { ADVISOR_QUESTION_MAX_LENGTH } from '@/lib/constants/advisor-question';
import { jsonResponse } from '@/test-utils/riskHeld';

vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: vi.fn(async () => true),
  markLocalBackendUnreachable: vi.fn(),
}));

import { askAdvisor } from '../copilot';

// A rare han character is one character to the server and two UTF-16 units to the browser.
const CHARACTER = '\u{20BB7}';

const answered = {
  data: {
    reply: 'ok',
    tier: 'tier0',
    message: { id: 'm1', role: 'assistant', content: 'ok', tier: 'tier0', created_at: '' },
  },
};

/** The question the request carried. */
async function sentQuestion(question: string): Promise<string> {
  let body = '';
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      body = String(init?.body);
      return jsonResponse(200, answered);
    }),
  );
  await askAdvisor('chat-1', question);
  return (JSON.parse(body) as { question: string }).question;
}

describe('asking the session advisor a long question', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('cuts it to the length the server accepts, counted in characters', async () => {
    const sent = await sentQuestion(CHARACTER.repeat(ADVISOR_QUESTION_MAX_LENGTH + 5));

    expect(sent).toBe(CHARACTER.repeat(ADVISOR_QUESTION_MAX_LENGTH));
  });

  it('sends a question within the limit as it is', async () => {
    expect(await sentQuestion('what next?')).toBe('what next?');
  });
});
