import { beforeEach, describe, expect, it, vi } from 'vitest';

const toastMock = vi.hoisted(() =>
  Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
);

vi.mock('@/lib/utils/toast', () => ({ toast: toastMock }));

/** The service keeps the translator in module state, so every test loads a fresh copy. */
async function loadService() {
  vi.resetModules();
  return import('../i18nToastService');
}

describe('translateI18nKey', () => {
  it('returns the key itself before a translator is installed', async () => {
    const { translateI18nKey } = await loadService();
    expect(translateI18nKey('common.clipboard.copied')).toBe('common.clipboard.copied');
  });

  it('keeps honouring an explicit fallback before a translator is installed', async () => {
    const { translateI18nKey } = await loadService();
    expect(translateI18nKey('common.clipboard.copied', 'Copied')).toBe('Copied');
  });

  it('resolves the key once a translator is installed', async () => {
    const { setGlobalTranslator, translateI18nKey } = await loadService();
    setGlobalTranslator((key) => `translated:${key}`);
    expect(translateI18nKey('common.clipboard.copied', 'Copied')).toBe('translated:common.clipboard.copied');
  });
});

describe('showI18nToast', () => {
  beforeEach(() => {
    toastMock.mockClear();
    toastMock.info.mockClear();
    toastMock.error.mockClear();
  });

  it('translates title, values and action label, and honours type and duration', async () => {
    const { setGlobalTranslator, showI18nToast } = await loadService();
    const translator = vi.fn((key: string) => `translated:${key}`);
    setGlobalTranslator(translator);
    const onClick = vi.fn();

    showI18nToast(
      'chat.cacheResetNotice',
      { reason: 'prompt changed', tokens: 0 },
      { type: 'info', duration: 5000, action: { label: 'agent.configEditor.goToSettings', onClick } },
    );

    expect(translator).toHaveBeenCalledWith('chat.cacheResetNotice', { reason: 'prompt changed', tokens: 0 });
    expect(toastMock.info).toHaveBeenCalledWith('translated:chat.cacheResetNotice', {
      description: undefined,
      duration: 5000,
      action: { label: 'translated:agent.configEditor.goToSettings', onClick },
    });
  });

  it('shows a default toast for 3 seconds when no type or duration is given', async () => {
    const { setGlobalTranslator, showI18nToast } = await loadService();
    setGlobalTranslator((key) => `translated:${key}`);

    showI18nToast('common.clipboard.copied');

    expect(toastMock).toHaveBeenCalledWith('translated:common.clipboard.copied', {
      description: undefined,
      duration: 3000,
    });
  });
});
