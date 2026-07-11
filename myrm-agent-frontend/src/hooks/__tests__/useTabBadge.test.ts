// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';

let mockLivenessState = 'idle';
let mockTitleFlashing = false;

vi.mock('@/hooks/useLivenessState', () => ({
  useLivenessState: () => ({
    state: mockLivenessState,
    activeCount: mockLivenessState === 'busy' ? 1 : 0,
    tooltip: '',
  }),
}));

vi.mock('@/lib/approval/approvalAlertService', () => ({
  isTitleFlashing: () => mockTitleFlashing,
}));

describe('useTabBadge', () => {
  beforeEach(() => {
    mockLivenessState = 'idle';
    mockTitleFlashing = false;
    document.title = 'MyrmAgent';
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does not add prefix when idle', async () => {
    mockLivenessState = 'idle';
    const { useTabBadge } = await import('../useTabBadge');
    renderHook(() => useTabBadge());
    expect(document.title).toBe('MyrmAgent');
  });

  it('adds [*] prefix when busy', async () => {
    mockLivenessState = 'busy';
    const { useTabBadge } = await import('../useTabBadge');
    renderHook(() => useTabBadge());
    expect(document.title).toBe('[*] MyrmAgent');
  });

  it('adds [!] prefix when degraded', async () => {
    mockLivenessState = 'degraded';
    const { useTabBadge } = await import('../useTabBadge');
    renderHook(() => useTabBadge());
    expect(document.title).toBe('[!] MyrmAgent');
  });

  it('yields to approval title flashing', async () => {
    mockLivenessState = 'busy';
    mockTitleFlashing = true;
    document.title = 'Original Title';
    const { useTabBadge } = await import('../useTabBadge');
    renderHook(() => useTabBadge());
    expect(document.title).toBe('Original Title');
  });

  it('restores title on unmount', async () => {
    mockLivenessState = 'busy';
    const { useTabBadge } = await import('../useTabBadge');
    const { unmount } = renderHook(() => useTabBadge());
    expect(document.title).toBe('[*] MyrmAgent');
    unmount();
    expect(document.title).toBe('MyrmAgent');
  });
});
