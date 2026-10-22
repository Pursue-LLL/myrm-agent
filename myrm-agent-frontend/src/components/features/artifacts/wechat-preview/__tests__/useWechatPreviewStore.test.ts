import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { useWechatPreviewStore } from '../useWechatPreviewStore';

describe('useWechatPreviewStore', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useWechatPreviewStore.getState().reset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('initializes with default mobile, classic theme, normal scale, and false copied', () => {
    const state = useWechatPreviewStore.getState();
    expect(state.viewport).toBe('mobile');
    expect(state.themeId).toBe('classic');
    expect(state.scale).toBe('normal');
    expect(state.copied).toBe(false);
  });

  it('updates viewport properly across mobile, tablet, and desktop', () => {
    const store = useWechatPreviewStore.getState();
    store.setViewport('tablet');
    expect(useWechatPreviewStore.getState().viewport).toBe('tablet');

    store.setViewport('desktop');
    expect(useWechatPreviewStore.getState().viewport).toBe('desktop');

    store.setViewport('mobile');
    expect(useWechatPreviewStore.getState().viewport).toBe('mobile');
  });

  it('updates themeId across presets', () => {
    const store = useWechatPreviewStore.getState();
    store.setThemeId('tech');
    expect(useWechatPreviewStore.getState().themeId).toBe('tech');

    store.setThemeId('enterprise');
    expect(useWechatPreviewStore.getState().themeId).toBe('enterprise');

    store.setThemeId('humanist');
    expect(useWechatPreviewStore.getState().themeId).toBe('humanist');
  });

  it('updates font size scale properly', () => {
    const store = useWechatPreviewStore.getState();
    store.setScale('compact');
    expect(useWechatPreviewStore.getState().scale).toBe('compact');

    store.setScale('spacious');
    expect(useWechatPreviewStore.getState().scale).toBe('spacious');
  });

  it('triggers copied feedback with automatic 2-second timeout reset', () => {
    const store = useWechatPreviewStore.getState();
    expect(store.copied).toBe(false);

    store.triggerCopiedFeedback();
    expect(useWechatPreviewStore.getState().copied).toBe(true);

    vi.advanceTimersByTime(1999);
    expect(useWechatPreviewStore.getState().copied).toBe(true);

    vi.advanceTimersByTime(2);
    expect(useWechatPreviewStore.getState().copied).toBe(false);
  });

  it('resets state back to default configuration', () => {
    const store = useWechatPreviewStore.getState();
    store.setViewport('tablet');
    store.setThemeId('humanist');
    store.setScale('spacious');
    store.setCopied(true);

    store.reset();
    const resetState = useWechatPreviewStore.getState();
    expect(resetState.viewport).toBe('mobile');
    expect(resetState.themeId).toBe('classic');
    expect(resetState.scale).toBe('normal');
    expect(resetState.copied).toBe(false);
  });
});
