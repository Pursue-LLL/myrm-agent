import { beforeEach, describe, expect, it, vi } from 'vitest';

const isLocalModeMock = vi.hoisted(() => vi.fn(() => false));

vi.mock('@/lib/deploy-mode', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
  return {
    ...actual,
    isLocalMode: () => isLocalModeMock(),
  };
});

import {
  resolveWebSearchConfigGapActionLabel,
  resolveWebSearchConfigGapActionLabelKey,
  runWebSearchConfigGapAction,
  SEARCH_SETTINGS_PATH,
} from '@/store/config/webSearchConfigGap';

describe('webSearchConfigGap', () => {
  beforeEach(() => {
    isLocalModeMock.mockReturnValue(false);
    document.documentElement.lang = 'en';
  });

  it('exports default settings path', () => {
    expect(SEARCH_SETTINGS_PATH).toBe('/settings/search');
  });

  it('resolveWebSearchConfigGapActionLabelKey uses settings key in cloud mode', () => {
    expect(resolveWebSearchConfigGapActionLabelKey()).toBe('chat.searchNotConfigured.action');
  });

  it('resolveWebSearchConfigGapActionLabelKey uses local enable key in local mode', () => {
    isLocalModeMock.mockReturnValue(true);
    expect(resolveWebSearchConfigGapActionLabelKey()).toBe('chat.searchNotConfigured.enableAction');
  });

  it('resolveWebSearchConfigGapActionLabel uses cloud copy in en', () => {
    expect(resolveWebSearchConfigGapActionLabel(false)).toBe('Go to Settings');
  });

  it('resolveWebSearchConfigGapActionLabel uses local quick-enable copy when local mode', () => {
    isLocalModeMock.mockReturnValue(true);
    document.documentElement.lang = 'zh-CN';
    expect(resolveWebSearchConfigGapActionLabel()).toBe('一键启用免费搜索');
  });

  it('runWebSearchConfigGapAction navigates to settings when not local', async () => {
    const assign = vi.fn();
    Object.defineProperty(window, 'location', {
      value: { assign },
      configurable: true,
    });

    await runWebSearchConfigGapAction('/settings/search');

    expect(assign).toHaveBeenCalledWith('/settings/search');
  });
});
