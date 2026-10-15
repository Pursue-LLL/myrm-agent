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

import { askAdvisor } from '../copilot';

function stubFetch(status: number, body: unknown): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => jsonResponse(status, body)),
  );
}

describe('asking the session advisor a question the server holds', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installEnglishToastTranslator();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows the one localized notice and hands the caller no answer', async () => {
    stubFetch(400, riskHeldRefusalBody);

    const answer = await askAdvisor('chat-1', 'use key sk-AAAAAABBBBBBCCCCCCDDDD-0');

    expect(answer).toBeNull();
    expect(toastMock.error).toHaveBeenCalledTimes(1);
    expect(toastMock.error.mock.calls[0]?.[0]).toBe(riskHeldTitle);
  });

  it('shows no notice for any other failure', async () => {
    stubFetch(500, { detail: 'boom' });

    expect(await askAdvisor('chat-1', 'what next?')).toBeNull();
    expect(toastMock.error).not.toHaveBeenCalled();
  });
});
