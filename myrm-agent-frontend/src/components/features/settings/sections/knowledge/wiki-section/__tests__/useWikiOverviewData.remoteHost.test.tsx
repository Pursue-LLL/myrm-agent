/**
 * @vitest-environment jsdom
 * @vitest-environment-options {"url": "https://wiki.example.com/settings"}
 */
import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { settle } from '@/test-utils/fakeClock';
import { resetKit, service } from './wikiSectionTestKit';
import { healthOf, statsOf } from './wikiSectionFixtures';
import { useWikiOverviewData } from '../useWikiOverviewData';

const registerHandlers = vi.fn();

beforeEach(() => {
  resetKit();
  registerHandlers.mockClear();
  Object.assign(window, { __MYRM_E2E_WIKI__: { registerHandlers, unregisterHandlers: vi.fn() } });
});

afterEach(() => {
  cleanup();
  Reflect.deleteProperty(window, '__MYRM_E2E_WIKI__');
});

describe('useWikiOverviewData on a deployed host', () => {
  it('runs on a host other than localhost', () => {
    expect(window.location.hostname).toBe('wiki.example.com');
  });

  it('exposes no E2E injection: no handlers are registered and the test events are ignored', async () => {
    const { result } = renderHook(() => useWikiOverviewData(null, 'overview'));
    await settle();
    expect(registerHandlers).not.toHaveBeenCalled();

    const before = result.current.stats;
    await act(async () => {
      window.dispatchEvent(new CustomEvent('myrm-e2e-wiki-stats', { detail: statsOf({ total_concepts: 999 }) }));
      window.dispatchEvent(new CustomEvent('myrm-e2e-wiki-health-report', { detail: healthOf({ issues_found: 99 }) }));
    });
    expect(result.current.stats).toBe(before);
    expect(result.current.healthReport).toEqual(healthOf());
    expect(service.getHealthReport).toHaveBeenCalledOnce();
  });
});
