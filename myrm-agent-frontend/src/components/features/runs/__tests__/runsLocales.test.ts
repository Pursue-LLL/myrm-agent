import { describe, expect, it } from 'vitest';
import deRuns from '../../../../../locales/namespaces/de/runs.json';
import deNav from '../../../../../locales/namespaces/de/nav.json';
import enRuns from '../../../../../locales/namespaces/en/runs.json';
import enNav from '../../../../../locales/namespaces/en/nav.json';
import jaRuns from '../../../../../locales/namespaces/ja/runs.json';
import jaNav from '../../../../../locales/namespaces/ja/nav.json';
import koRuns from '../../../../../locales/namespaces/ko/runs.json';
import koNav from '../../../../../locales/namespaces/ko/nav.json';
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
  { name: 'ja', runs: jaRuns, nav: jaNav },
  { name: 'ko', runs: koRuns, nav: koNav },
  { name: 'de', runs: deRuns, nav: deNav },
] as const;

describe('runs locale keys', () => {
  it.each(LOCALES)('$name namespace files have complete runs keys and nav.runs', ({ runs, nav }) => {
    for (const key of REQUIRED_RUNS_KEYS) {
      expect(runs[key as keyof typeof runs], `runs.${key}`).toBeTruthy();
    }

    expect(nav.runs).toBeTruthy();
  });
});
