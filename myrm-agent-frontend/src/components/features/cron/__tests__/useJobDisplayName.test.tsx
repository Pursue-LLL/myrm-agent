import { describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';

const stableT = (key: string) => `heartbeat.${key}`;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

import { HEARTBEAT_JOB_NAME } from '../cron-utils';
import { useJobDisplayName } from '../useJobDisplayName';

describe('useJobDisplayName', () => {
  it('names the heartbeat by its title instead of its reserved stored name', () => {
    const { result } = renderHook(() => useJobDisplayName());

    expect(result.current(HEARTBEAT_JOB_NAME)).toBe('heartbeat.title');
  });

  it.each(['Daily digest', 'heartbeat', '__other__'])('leaves the job name %s as the user wrote it', (name) => {
    const { result } = renderHook(() => useJobDisplayName());

    expect(result.current(name)).toBe(name);
  });

  it('hands out the same function while the translator stays the same', () => {
    const { result, rerender } = renderHook(() => useJobDisplayName());
    const first = result.current;

    rerender();

    expect(result.current).toBe(first);
  });
});
