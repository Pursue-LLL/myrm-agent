import { renderHook } from '@testing-library/react';
import { vi } from 'vitest';

import { useWikiMaintenance } from '../useWikiMaintenance';
import type { WikiOverviewData } from '../useWikiOverviewData';

type Overview = Pick<
  WikiOverviewData,
  | 'loadStats'
  | 'setCompileRun'
  | 'markCompileRequested'
  | 'setHealthReport'
  | 'setHealthReportExpanded'
  | 'bumpTreeSync'
  | 'ingestSnapshot'
>;

/** 以可观察的总览回调渲染维护 hook；须在 wikiSectionTestKit 之后 import，hook 才会拿到 mock 的依赖。 */
export function renderMaintenance(scope: string | null = null, ingestSnapshot: Overview['ingestSnapshot'] = null) {
  const overview: Overview = {
    loadStats: vi.fn().mockResolvedValue(undefined),
    setCompileRun: vi.fn(),
    markCompileRequested: vi.fn(),
    setHealthReport: vi.fn(),
    setHealthReportExpanded: vi.fn(),
    bumpTreeSync: vi.fn(),
    ingestSnapshot,
  };
  const handleWikiTabChange = vi.fn();
  const rendered = renderHook(() => useWikiMaintenance({ agentScopeId: scope, overview, handleWikiTabChange }));
  return { ...rendered, overview, handleWikiTabChange };
}
