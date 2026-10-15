import { describe, expect, it, vi } from 'vitest';

import {
  SCAN_SEVERITIES,
  SCAN_THREAT_TYPES,
  parseRiskSignals,
  riskRemediation,
  riskSignalLabel,
  severityLabel,
  threatTypeLabel,
  type ScanRiskTranslate,
} from '@/lib/skills/scanRiskText';
import de from '../../../../locales/de.json';
import en from '../../../../locales/en.json';
import ja from '../../../../locales/ja.json';
import ko from '../../../../locales/ko.json';
import zhTW from '../../../../locales/zh-TW.json';
import zh from '../../../../locales/zh.json';

// The global test setup replaces next-intl. The real translator runs over the shipped messages so a missing key,
// a broken placeholder or a locale that drifted shows up exactly as it would in the product.
const { createTranslator } = await vi.importActual<typeof import('next-intl')>('next-intl');

const locales = { en, zh, 'zh-TW': zhTW, ja, ko, de } as const;
type LocaleName = keyof typeof locales;
const localeNames = Object.keys(locales) as LocaleName[];

function scanRiskTranslator(locale: LocaleName): ScanRiskTranslate {
  return createTranslator({
    locale,
    messages: locales[locale],
    namespace: 'settings.skills.scanRisk',
  }) as unknown as ScanRiskTranslate;
}

const SIGNALS = [
  'new_high_finding:data_exfiltration',
  'scan_unavailable',
  'diff_range:73%',
  'low_effective_rate:20%(5runs)',
] as const;

describe('parseRiskSignals', () => {
  it('reads the signals behind a risk reason code', () => {
    expect(parseRiskSignals('risk:new_high_finding:data_exfiltration,diff_range:73%')).toEqual([
      'new_high_finding:data_exfiltration',
      'diff_range:73%',
    ]);
  });

  it.each([null, undefined, '', 'manual_review', 'runtime_failure', 'risk:'])('has no signals for %s', (reasonCode) => {
    expect(parseRiskSignals(reasonCode)).toEqual([]);
  });
});

describe('scan risk copy', () => {
  it('speaks every locale with the same set of threat classes, signals and remediations', () => {
    const reference = en.settings.skills.scanRisk;
    for (const locale of localeNames) {
      const copy = locales[locale].settings.skills.scanRisk;
      expect(Object.keys(copy.threat).sort(), locale).toEqual(Object.keys(reference.threat).sort());
      expect(Object.keys(copy.severity).sort(), locale).toEqual(Object.keys(reference.severity).sort());
      expect(Object.keys(copy.signal).sort(), locale).toEqual(Object.keys(reference.signal).sort());
      expect(Object.keys(copy.remediation).sort(), locale).toEqual(Object.keys(reference.remediation).sort());
    }
  });

  it('keeps the threat and severity vocabulary in step with the shipped copy', () => {
    const { threat, severity } = en.settings.skills.scanRisk;

    expect([...SCAN_THREAT_TYPES, 'unknown'].sort()).toEqual(Object.keys(threat).sort());
    expect([...SCAN_SEVERITIES].sort()).toEqual(Object.keys(severity).sort());
  });

  it.each(localeNames)('[%s] gives every known threat class a readable name instead of its code', (locale) => {
    const t = scanRiskTranslator(locale);
    for (const code of SCAN_THREAT_TYPES) {
      const label = threatTypeLabel(t, code);
      expect(label.trim(), `${locale}.${code}`).not.toBe('');
      expect(label, `${locale}.${code}`).not.toContain('_');
      expect(label, `${locale}.${code}`).not.toContain('threat.');
    }
  });

  it.each(localeNames)('[%s] names an unknown threat class generically and never leaks its code', (locale) => {
    const t = scanRiskTranslator(locale);

    const label = threatTypeLabel(t, 'brand_new_class');

    expect(label).toBe(locales[locale].settings.skills.scanRisk.threat.unknown);
    expect(label).not.toContain('brand_new_class');
  });

  it.each(['constructor', '__proto__', 'toString', 'hasOwnProperty'])(
    'does not mistake the object-prototype member %s for a threat class or severity',
    (code) => {
      const t = scanRiskTranslator('en');

      expect(threatTypeLabel(t, code)).toBe(en.settings.skills.scanRisk.threat.unknown);
      expect(severityLabel(t, code)).toBe(code);
    },
  );

  it.each(localeNames)('[%s] translates every severity and shows an unknown one as sent', (locale) => {
    const t = scanRiskTranslator(locale);
    for (const severity of SCAN_SEVERITIES) {
      expect(severityLabel(t, severity)).not.toBe(severity);
    }
    expect(severityLabel(t, 'weird')).toBe('weird');
  });

  it.each(localeNames)('[%s] words each risk signal in plain language with its values filled in', (locale) => {
    const t = scanRiskTranslator(locale);

    const labels = SIGNALS.map((signal) => riskSignalLabel(t, signal));

    expect(labels[0]).toContain(threatTypeLabel(t, 'data_exfiltration'));
    expect(labels[2]).toContain('73%');
    expect(labels[3]).toContain('20%');
    expect(labels[3]).toContain('5');
    for (const label of labels) {
      expect(label).not.toMatch(/[{}]|new_high_finding|scan_unavailable|diff_range|low_effective_rate/);
    }
    expect(new Set(labels).size).toBe(SIGNALS.length);
  });

  it.each(localeNames)('[%s] words an unrecognised signal generically', (locale) => {
    const t = scanRiskTranslator(locale);

    expect(riskSignalLabel(t, 'something_new:42')).toBe(locales[locale].settings.skills.scanRisk.signal.unknown);
  });
});

describe('riskRemediation', () => {
  it.each(localeNames)('[%s] gives one sentence per kind of signal and ignores unknown ones', (locale) => {
    const t = scanRiskTranslator(locale);

    const sentences = riskRemediation(t, [...SIGNALS, 'something_new:42']);

    expect(sentences).toHaveLength(SIGNALS.length);
    expect(new Set(sentences).size).toBe(SIGNALS.length);
    for (const sentence of sentences) {
      expect(sentence).not.toContain('remediation.');
    }
  });

  it('does not repeat a sentence when the same kind of signal arrives twice', () => {
    const t = scanRiskTranslator('en');

    expect(riskRemediation(t, ['new_high_finding:data_exfiltration', 'new_high_finding:privilege_escalation'])).toEqual(
      [en.settings.skills.scanRisk.remediation.newHighFinding],
    );
  });

  it('adds nothing for signals it does not recognise', () => {
    expect(riskRemediation(scanRiskTranslator('en'), ['something_new:42'])).toEqual([]);
  });
});
