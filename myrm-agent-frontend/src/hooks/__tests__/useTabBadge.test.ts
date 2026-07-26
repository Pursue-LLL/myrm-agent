/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';

let mockLivenessState = 'idle';

vi.mock('@/hooks/useLivenessState', () => ({
  useLivenessState: () => ({
    state: mockLivenessState,
    activeCount: 0,
    tooltip: '',
  }),
}));

vi.mock('@/lib/approval/approvalAlertService', () => ({
  isTitleFlashing: () => false,
}));

describe('useTabBadge', () => {
  beforeEach(() => {
    mockLivenessState = 'idle';
    document.title = 'Myrm';
  });

  afterEach(() => {
    vi.restoreAllMocks();
    document.title = '';
  });

  it('does not prefix title when idle', async () => {
    const { useTabBadge } = await import('../useTabBadge');
    renderHook(() => useTabBadge());
    expect(document.title).toBe('Myrm');
  });

  it('prefixes [*] when busy', async () => {
    mockLivenessState = 'busy';
    const { useTabBadge } = await import('../useTabBadge');
    renderHook(() => useTabBadge());
    expect(document.title).toBe('[*] Myrm');
  });

  it('prefixes [!] when degraded', async () => {
    mockLivenessState = 'degraded';
    const { useTabBadge } = await import('../useTabBadge');
    renderHook(() => useTabBadge());
    expect(document.title).toBe('[!] Myrm');
  });

  it('prefixes [↓] when draining', async () => {
    mockLivenessState = 'draining';
    const { useTabBadge } = await import('../useTabBadge');
    renderHook(() => useTabBadge());
    expect(document.title).toBe('[↓] Myrm');
  });

  it('prefixes [×] when offline', async () => {
    mockLivenessState = 'offline';
    const { useTabBadge } = await import('../useTabBadge');
    renderHook(() => useTabBadge());
    expect(document.title).toBe('[×] Myrm');
  });
});
