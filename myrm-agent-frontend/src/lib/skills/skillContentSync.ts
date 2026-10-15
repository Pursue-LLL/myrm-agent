/**
 * [INPUT]
 * - Browser CustomEvent API
 *
 * [OUTPUT]
 * - notifySkillContentChanged: broadcast skill file mutations (e.g. batch undo)
 * - SKILL_CONTENT_CHANGED_EVENT: event name constant
 *
 * [POS]
 * Cross-surface skill content refresh signal (chat undo → open skill detail sheet).
 */

export const SKILL_CONTENT_CHANGED_EVENT = 'myrm-skill-content-changed';

export type SkillContentChangedDetail = {
  skillIds?: string[];
};

export function notifySkillContentChanged(skillIds?: string[]): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.dispatchEvent(
    new CustomEvent<SkillContentChangedDetail>(SKILL_CONTENT_CHANGED_EVENT, {
      detail: { skillIds },
    }),
  );
}
