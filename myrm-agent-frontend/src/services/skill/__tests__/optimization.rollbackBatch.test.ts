import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { rollbackSkillMutationBatch } from '../optimization';

const toastMock = vi.hoisted(() =>
  Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
);

vi.mock('@/lib/utils/toast', () => ({ toast: toastMock }));

vi.mock('@/lib/deploy-mode', () => ({
  getApiBaseUrl: () => 'http://127.0.0.1:8080/api/v1',
  getBackendBaseUrl: () => 'http://127.0.0.1:8080',
  shouldRedirectToLoginOnAuthFailure: () => true,
  isLocalMode: vi.fn(() => true),
  resolveE2eApiBase: () => '',
}));

vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: () => Promise.resolve(true),
  markLocalBackendUnreachable: () => undefined,
}));

vi.mock('@/lib/local-backend-dev', () => ({
  BACKEND_UNREACHABLE_CODE: 'BACKEND_UNREACHABLE',
  resolveBackendUnreachableMessage: () => Promise.resolve('Backend not reachable.'),
}));

vi.mock('@/store/useConfigStore', () => ({
  default: { getState: () => ({ personalSettings: undefined }) },
}));

describe('rollbackSkillMutationBatch', () => {
  const originalWindow = globalThis.window;
  const originalFetch = globalThis.fetch;
  const fetchMock = vi.fn<typeof fetch>();

  const respondWithError = (status: number, body: unknown) => {
    const text = () => Promise.resolve(JSON.stringify(body));
    fetchMock.mockResolvedValue({
      ok: false,
      status,
      text,
      clone: () => ({ text }),
      headers: new Headers(),
    } as Response);
  };

  beforeEach(async () => {
    toastMock.error.mockClear();
    toastMock.warning.mockClear();
    const { setGlobalTranslator } = await import('@/services/i18nToastService');
    setGlobalTranslator(Object.assign((key: string) => key, { has: () => false }));
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: { location: { href: '', pathname: '/test', search: '', hash: '' } } as Window & typeof globalThis,
    });
    Object.defineProperty(globalThis, 'fetch', { configurable: true, value: fetchMock });
  });

  afterEach(() => {
    Object.defineProperty(globalThis, 'window', { configurable: true, value: originalWindow });
    Object.defineProperty(globalThis, 'fetch', { configurable: true, value: originalFetch });
    fetchMock.mockReset();
  });

  it('posts to the rollback route of the batch and returns the restore count', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve({ batch_id: 'batch-1', skills_restored: 2, status: 'rolled_back' }),
    } as Response);

    await expect(rollbackSkillMutationBatch('batch-1')).resolves.toEqual({
      batch_id: 'batch-1',
      skills_restored: 2,
      status: 'rolled_back',
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe('http://127.0.0.1:8080/api/v1/skill-optimization/mutations/batch-1/rollback');
    expect(init?.method).toBe('POST');
  });

  it('hands the server error code to the caller, which words the failure itself', async () => {
    respondWithError(409, { detail: { code: 'batch_already_consumed', message: 'Batch already rolled back' } });

    await expect(rollbackSkillMutationBatch('batch-1')).rejects.toMatchObject({
      data: { code: 'batch_already_consumed' },
    });
  });

  it('leaves every failure toast to the caller, so one failed undo shows one toast', async () => {
    respondWithError(500, { detail: 'Skill store unavailable' });

    await expect(rollbackSkillMutationBatch('batch-1')).rejects.toBeDefined();
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(toastMock.error).not.toHaveBeenCalled();
    expect(toastMock.warning).not.toHaveBeenCalled();
  });
});
