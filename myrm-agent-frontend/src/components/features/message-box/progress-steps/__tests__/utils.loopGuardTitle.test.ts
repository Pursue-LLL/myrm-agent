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

  describe.each(Object.entries(CATALOGS))('%s', (_locale, messages) => {
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

    it('words the toast that tells the user the agent was stopped', () => {
      expect(copy('loop_guard_break_toast').trim()).not.toBe('');
    });
  });
});
