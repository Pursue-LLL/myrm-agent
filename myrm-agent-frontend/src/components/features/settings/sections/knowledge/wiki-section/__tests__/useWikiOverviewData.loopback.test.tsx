/**
 * @vitest-environment jsdom
 * @vitest-environment-options {"url": "http://127.0.0.1:3000/settings"}
 */
import { cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { settle } from '@/test-utils/fakeClock';
import { resetKit } from './wikiSectionTestKit';
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

describe('useWikiOverviewData on the loopback address', () => {
  it('runs on 127.0.0.1', () => {
    expect(window.location.hostname).toBe('127.0.0.1');
  });

  it('registers the E2E handlers, as it does on localhost', async () => {
    renderHook(() => useWikiOverviewData(null, 'overview'));
    await settle();
    expect(registerHandlers).toHaveBeenCalledOnce();
  });
});
