import { describe, expect, it } from 'vitest';
import enRuns from '../../../../../locales/namespaces/en/runs.json';
import enNav from '../../../../../locales/namespaces/en/nav.json';
import zhRuns from '../../../../../locales/namespaces/zh/runs.json';
import zhNav from '../../../../../locales/namespaces/zh/nav.json';

const REQUIRED_RUNS_KEYS = [
  'title',
  'subtitle',
  'totalRuns',
  'filterAll',
  'filterRunning',
  'filterOk',
  'filterError',
  'sourceAll',
  'sourceCron',
  'sourceKanban',
  'sourceShell',
  'empty',
  'emptyFiltered',
  'degradedBanner',
  'loadError',
  'retry',
  'executionStepsBadge',
  'executionTrace',
  'loadMore',
  'timeJustNow',
  'timeMinutesAgo',
  'timeHoursAgo',
  'timeDaysAgo',
  'executionSteps',
] as const;

const LOCALES = [
  { name: 'en', runs: enRuns, nav: enNav },
  { name: 'zh', runs: zhRuns, nav: zhNav },
] as const;

describe('runs locale keys', () => {
  it.each(LOCALES)('$name namespace files have complete runs keys and nav.runs', ({ runs, nav }) => {
    for (const key of REQUIRED_RUNS_KEYS) {
      expect(runs[key as keyof typeof runs], `runs.${key}`).toBeTruthy();
    }

    expect(nav.runs).toBeTruthy();
  });
});
