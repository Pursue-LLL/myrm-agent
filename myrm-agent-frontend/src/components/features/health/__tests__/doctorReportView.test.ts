import { describe, expect, it } from 'vitest';

import type { HealthReport } from '@/services/runtime-health';
import { DOCTOR_LOCALE_KEYS, describeReport } from '../doctorReportView';

const MAPPED_CODE_KEY = 'errors.ERR_MAPPED.message';
const localeKeys = new Set<string>([...DOCTOR_LOCALE_KEYS, MAPPED_CODE_KEY]);
const hasKey = (key: string) => localeKeys.has(key);

const report = (overrides: Partial<HealthReport>): HealthReport => ({
  component_name: 'Network',
  status: 'fail',
  message: 'Internet is not available.',
  ...overrides,
});

const technicalLabels = (view: ReturnType<typeof describeReport>) => view.technical.map((line) => line.labelKey);

describe('describeReport summary', () => {
  it('prefers the locale text of a verdict code and hands the meta data to it', () => {
    const view = describeReport(report({ code: 'ERR_MAPPED', meta_data: { missing: 'Screen Recording' } }), hasKey);

    expect(view.summary).toEqual({ key: MAPPED_CODE_KEY, values: { missing: 'Screen Recording' } });
    // The English original stays reachable through the technical lines.
    expect(view.technical).toContainEqual({ labelKey: 'technical.message', value: 'Internet is not available.' });
  });

  it('falls through to the component hint when the code has no locale entry', () => {
    const view = describeReport(report({ code: 'ERR_UNMAPPED' }), hasKey);

    expect(view.summary).toEqual({ key: 'hints.Network.fail' });
  });

  it.each([
    ['a component without a dedicated hint', 'SkillEcosystem', 'warn', 'hints.generic.warn'],
    ['a status the component has no dedicated hint for', 'Network', 'warn', 'hints.generic.warn'],
    ['a failing component without a dedicated hint', 'DesktopLockedUse', 'fail', 'hints.generic.fail'],
  ] as const)('uses the generic hint for %s', (_label, componentName, status, expectedKey) => {
    const view = describeReport(report({ component_name: componentName, status }), hasKey);

    expect(view.summary).toEqual({ key: expectedKey });
  });

  it('uses the generic hint when the locale lacks the dedicated one', () => {
    const view = describeReport(report({}), (key) => key !== 'hints.Network.fail' && hasKey(key));

    expect(view.summary).toEqual({ key: 'hints.generic.fail' });
  });

  it('keeps the backend message of a passing report, which is what the user needs to read', () => {
    const view = describeReport(report({ status: 'pass', message: 'Database is healthy.' }), hasKey);

    expect(view.summary).toEqual({ text: 'Database is healthy.' });
    expect(technicalLabels(view)).not.toContain('technical.message');
  });
});

describe('describeReport title', () => {
  it('localizes a known component and keeps its raw name for support', () => {
    const view = describeReport(report({}), hasKey);

    expect(view.title).toEqual({ key: 'components.Network' });
    expect(view.technical[0]).toEqual({ labelKey: 'technical.component', value: 'Network' });
  });

  it.each(['check_network_health', 'unknown_hook', 'hook_3'])(
    'never shows the manager fallback function name %s',
    (name) => {
      const view = describeReport(report({ component_name: name }), hasKey);

      expect(view.title).toEqual({ key: 'components.generic' });
      expect(view.technical[0]).toEqual({ labelKey: 'technical.component', value: name });
    },
  );

  it('keeps an unknown readable component name so future probes stay distinguishable', () => {
    const view = describeReport(report({ component_name: 'FutureProbe' }), hasKey);

    expect(view.title).toEqual({ text: 'FutureProbe' });
    expect(technicalLabels(view)).not.toContain('technical.component');
  });

  it('keeps the raw name when the locale lacks the title of a known component', () => {
    const view = describeReport(report({}), (key) => !key.startsWith('components.') && hasKey(key));

    expect(view.title).toEqual({ text: 'Network' });
  });
});

describe('describeReport technical lines', () => {
  it('lists every populated technical field in a fixed order and skips empty ones', () => {
    const view = describeReport(
      report({
        component_name: 'SystemExhaustion',
        status: 'warn',
        message: 'Swap/Pagefile usage is high.',
        detail: 'Swap/Pagefile: 93.6%',
        measured: 'Swap 93.6%',
        expected: 'Swap <70%',
        cause: 'Idle pages were moved to swap earlier.',
        fix_suggestion: 'Inspect orphan worker processes.',
      }),
      hasKey,
    );

    expect(technicalLabels(view)).toEqual([
      'technical.component',
      'technical.message',
      'technical.detail',
      'technical.measured',
      'technical.expected',
      'technical.cause',
      'technical.fix',
    ]);

    const sparse = describeReport(report({ detail: '', measured: null, cause: undefined }), hasKey);
    expect(technicalLabels(sparse)).toEqual(['technical.component', 'technical.message']);
  });
});

describe('DOCTOR_LOCALE_KEYS', () => {
  it('lists each key once', () => {
    expect(new Set(DOCTOR_LOCALE_KEYS).size).toBe(DOCTOR_LOCALE_KEYS.length);
  });
});
