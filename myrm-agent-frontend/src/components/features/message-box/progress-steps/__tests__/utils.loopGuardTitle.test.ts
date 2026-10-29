/**
 * The loop guard steps are worded in every language the UI ships, not shown as raw keys or English.
 */
import { describe, expect, it } from 'vitest';

import de from '../../../../../../locales/de.json';
import en from '../../../../../../locales/en.json';
import ja from '../../../../../../locales/ja.json';
import ko from '../../../../../../locales/ko.json';
import zhTW from '../../../../../../locales/zh-TW.json';
import zh from '../../../../../../locales/zh.json';
import { getStepTitle } from '../utils';
import { loopGuardProgressStepKey } from '@/store/chat/messageStream/handlers/loopGuardStepKey';
import type { ProgressItem } from '@/store/chat/types';

const CATALOGS = { en, zh, 'zh-TW': zhTW, ja, ko, de } as const;

/**
 * A `loop_guard_break` blocks one repeated call and hands the error back to the model; the run goes on.
 * Wording that says the agent or the run was stopped would tell the user something that did not happen.
 */
const STOP_CLAIMS = {
  en: /stopp?ed|terminat|abort/i,
  zh: /停止|中止|终止/,
  'zh-TW': /停止|中止|終止/,
  ja: /停止|中止|終了/,
  ko: /중단|중지|종료/,
  de: /gestoppt|beendet|abgebrochen/i,
} as const;

const STEP_KEYS = [
  loopGuardProgressStepKey('loop_guard_warn', 'iteration_budget'),
  loopGuardProgressStepKey('loop_guard_warn', 'repetition'),
  loopGuardProgressStepKey('loop_guard_warn', undefined),
  loopGuardProgressStepKey('loop_guard_break', 'repetition'),
];

describe('loop guard step titles', () => {
  it('has four distinct step keys', () => {
    expect(new Set(STEP_KEYS).size).toBe(4);
  });

  describe.each(Object.entries(CATALOGS))('%s', (locale, messages) => {
    const progressSteps: Record<string, unknown> = messages.progressSteps;
    const copy = (key: string) => (typeof progressSteps[key] === 'string' ? progressSteps[key] : '');
    const t = (key: string) => copy(key) || key;

    it.each(STEP_KEYS)('titles %s from the catalog', (stepKey) => {
      const step: ProgressItem = { step_key: stepKey, items: [], status: 'warning' };

      const title = getStepTitle(step, t);

      expect(title).toBe(copy(stepKey));
      expect(title).not.toBe(stepKey);
      expect(title.trim()).not.toBe('');
    });

    it('words the pause after repeated tool failures from the catalog', () => {
      const step: ProgressItem = { step_key: 'tool_stuck_paused', items: [], status: 'error' };

      const title = getStepTitle(step, t);

      expect(title).toBe(copy('tool_stuck_paused'));
      expect(title.trim()).not.toBe('');
      expect(title).not.toBe('tool_stuck_paused');
    });

    it('words the blocked call and its toast without claiming the run stopped', () => {
      const stopClaim = STOP_CLAIMS[locale as keyof typeof STOP_CLAIMS];

      for (const key of ['loop_guard_break', 'loop_guard_break_toast']) {
        expect(copy(key).trim()).not.toBe('');
        expect(copy(key)).not.toMatch(stopClaim);
      }
    });
  });
});
