/** @vitest-environment jsdom */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render } from '@testing-library/react';
import { NextIntlClientProvider, type AbstractIntlMessages } from 'next-intl';
import { describe, expect, it, vi } from 'vitest';
import CuratorDiagnosticsSection from '../CuratorDiagnosticsSection';
import CuratorHistorySection from '../CuratorHistorySection';
import type { CuratorHistoryEntry, SkillDoctorDiagnosticsResponse } from '@/services/skill';

// The global setup stubs next-intl with an identity translator; this suite asserts the real locale copy.
vi.mock('next-intl', async (importOriginal) => importOriginal<typeof import('next-intl')>());

const LOCALES = ['en', 'zh', 'zh-TW', 'ja', 'ko', 'de'] as const;
type Locale = (typeof LOCALES)[number];

function messagesFor(locale: Locale): AbstractIntlMessages {
  const file = resolve(__dirname, `../../../../../locales/${locale}.json`);
  const { curator, card } = JSON.parse(readFileSync(file, 'utf8')).settings.skills;
  return { settings: { skills: { curator, card } } };
}

function renderIn(locale: Locale, ui: React.ReactElement) {
  return render(
    <NextIntlClientProvider locale={locale} messages={messagesFor(locale)}>
      {ui}
    </NextIntlClientProvider>,
  );
}

const noop = () => undefined;

const diagnostics: SkillDoctorDiagnosticsResponse = {
  total_skills: 12,
  active_skills: 12,
  stale_skills: 0,
  archived_skills: 0,
  pinned_skills: 1,
  health_score: 70,
  findings: [
    {
      skill_name: 'invoice-ocr',
      finding_type: 'wrong_but_frequent',
      severity: 'critical',
      call_count: 8,
      success_rate: 0.125,
      pinned: true,
      recommended_action: 'unpin_and_archive',
      details: { observed_count: 8, success_count: 1, failure_count: 7, trust: 'local' },
    },
    {
      skill_name: 'old-notes',
      finding_type: 'stale_pinned',
      severity: 'info',
      call_count: 3,
      success_rate: 1,
      pinned: true,
      recommended_action: 'unpin_and_archive',
      details: { days_inactive: 1 },
    },
    {
      skill_name: '[Library Bloat]',
      finding_type: 'hoarding_bloat',
      severity: 'warning',
      call_count: 0,
      success_rate: 1,
      pinned: false,
      recommended_action: 'archive',
      details: { active_count: 52, max_skills: 50, excess: 2 },
    },
  ],
};

const DAY_MS = 86_400_000;

const historyEntry: CuratorHistoryEntry = {
  timestamp: new Date(Date.now() - 3 * DAY_MS).toISOString(),
  trigger: 'background',
  duration_ms: 12,
  skills_scanned: 41,
  total_transitions: 4,
  stale_count: 2,
  archived_count: 2,
  skipped_pinned: 0,
  errors: [],
  transitions: [
    { skill_name: 'ppt-style', from_status: 'active', to_status: 'stale', reason: 'inactive' },
    { skill_name: 'old-report', from_status: 'stale', to_status: 'archived', reason: 'archive' },
    { skill_name: 'flaky-scraper', from_status: 'active', to_status: 'stale', reason: 'low_quality' },
    { skill_name: 'extra-skill', from_status: 'active', to_status: 'archived', reason: 'lru_eviction' },
  ],
};

/** Anything an English-only or developer-facing rendering would leak into a localized UI. */
const LEAKED_IDENTIFIERS = /PINNED|Score|stale|archived|inactive|low_quality|lru_eviction|\[Library Bloat\]|\bago\b/;
/** What a missing translation key degrades to. */
const MISSING_KEY_FALLBACK = /settings\.skills|historyReason|doctor\./;

describe('CuratorDiagnosticsSection', () => {
  it('phrases every finding from its type code and parameters in the active language', () => {
    const { container } = renderIn(
      'zh',
      <CuratorDiagnosticsSection diagnostics={diagnostics} remediatingSkill={null} onRemediate={noop} />,
    );
    const text = container.textContent ?? '';

    expect(text).toContain('已运行 8 次，成功率仅 12.5%');
    expect(text).toContain('已固定，但已有 1 天未使用');
    expect(text).toContain('活跃技能 52 个，比上限 50 个多出 2 个');
    expect(text).toContain('70/100');
    expect(text).not.toMatch(LEAKED_IDENTIFIERS);
  });

  it('pluralises the English phrasing', () => {
    const { container } = renderIn(
      'en',
      <CuratorDiagnosticsSection diagnostics={diagnostics} remediatingSkill={null} onRemediate={noop} />,
    );
    const text = container.textContent ?? '';

    expect(text).toContain('Ran 8 times with only 12.5% success');
    expect(text).toContain('Pinned but unused for 1 day');
    expect(text).toContain('52 active skills, 2 over the limit of 50');
  });

  it('offers no skill-level actions on the library-wide finding', () => {
    const { container } = renderIn(
      'en',
      <CuratorDiagnosticsSection diagnostics={diagnostics} remediatingSkill={null} onRemediate={noop} />,
    );

    // Each skill finding offers its remedy plus reset; the library-wide row offers nothing.
    const rows = container.querySelectorAll('[data-testid="curator-diagnostic-row"]');
    expect(Array.from(rows, (row) => row.querySelectorAll('button').length)).toEqual([2, 2, 0]);
  });

  it.each(LOCALES)('renders no developer identifiers or missing keys in %s', (locale) => {
    const { container } = renderIn(
      locale,
      <CuratorDiagnosticsSection diagnostics={diagnostics} remediatingSkill={null} onRemediate={noop} />,
    );
    const text = container.textContent ?? '';

    expect(text).not.toMatch(MISSING_KEY_FALLBACK);
    expect(text).not.toContain('[Library Bloat]');
    expect(text).not.toContain('PINNED');
  });
});

describe('CuratorHistorySection', () => {
  it('shows the outcome and the reason of each move in the active language', () => {
    const { container } = renderIn(
      'zh',
      <CuratorHistorySection open loading={false} entries={[historyEntry]} onToggle={noop} />,
    );
    const text = container.textContent ?? '';

    expect(container.querySelectorAll('[data-testid="curator-history-entry"]')).toHaveLength(1);
    expect(text).toContain('3天前');
    expect(text).toContain('闲置 2');
    expect(text).toContain('已归档 2');
    expect(text).toContain('ppt-style → 闲置(长期未使用)');
    expect(text).toContain('old-report → 已归档(长期未使用)');
    expect(text).toContain('flaky-scraper → 闲置(成功率偏低)');
    expect(text).toContain('extra-skill → 已归档(超出技能数量上限)');
    expect(text).not.toMatch(LEAKED_IDENTIFIERS);
  });

  it.each(LOCALES)('renders no developer identifiers or missing keys in %s', (locale) => {
    const { container } = renderIn(
      locale,
      <CuratorHistorySection open loading={false} entries={[historyEntry]} onToggle={noop} />,
    );
    const text = container.textContent ?? '';

    expect(text).not.toMatch(MISSING_KEY_FALLBACK);
    expect(text).not.toMatch(/lru_eviction|low_quality|inactive/);
    if (locale !== 'en') {
      expect(text).not.toMatch(/\bago\b|\bstale\b|\barchived\b/i);
    }
  });
});
