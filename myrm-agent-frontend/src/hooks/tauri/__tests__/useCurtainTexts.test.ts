/**
 * [INPUT]
 * - @/hooks/tauri/useCurtainTexts
 * - @/lib/deploy-mode::isTauriRuntime
 * - next-intl::useTranslations
 *
 * [OUTPUT]
 * - Unit test suite for the privacy curtain board text injection hook
 *
 * [POS]
 * Verifies locale-driven board text injection into the Rust curtain cache on
 * Tauri and a safe no-op on the web runtime.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useCurtainTexts } from '../useCurtainTexts';
import * as deployMode from '@/lib/deploy-mode';

const invokeMock = vi.fn(() => Promise.resolve());

vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => invokeMock(...args),
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => `text:${key}`,
}));

describe('useCurtainTexts', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    invokeMock.mockClear();
  });

  it('does not invoke on the web runtime', async () => {
    vi.spyOn(deployMode, 'isTauriRuntime').mockReturnValue(false);

    renderHook(() => useCurtainTexts());
    await Promise.resolve();

    expect(invokeMock).not.toHaveBeenCalled();
  });

  it('injects the three localized board texts on the Tauri runtime', async () => {
    vi.spyOn(deployMode, 'isTauriRuntime').mockReturnValue(true);

    renderHook(() => useCurtainTexts());
    await vi.waitFor(() => expect(invokeMock).toHaveBeenCalled());

    expect(invokeMock).toHaveBeenCalledWith('curtain_set_texts', {
      texts: {
        primary: 'text:primary',
        sub: 'text:sub',
        hint: 'text:hint',
      },
    });
  });

  it('swallows injection failures without throwing', async () => {
    vi.spyOn(deployMode, 'isTauriRuntime').mockReturnValue(true);
    invokeMock.mockRejectedValueOnce(new Error('bridge down'));
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    renderHook(() => useCurtainTexts());
    await vi.waitFor(() => expect(errorSpy).toHaveBeenCalled());

    expect(errorSpy.mock.calls[0][0]).toContain('Failed to inject curtain texts');
  });
});
