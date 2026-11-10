import { describe, expect, it, vi } from 'vitest';

import { showSystemNotificationToast } from '@/hooks/globalEvents/systemNotificationToast';

const LEVELS = ['success', 'info', 'warning', 'error'] as const;
const TOAST_OPTIONS = { description: 'Body', duration: 10_000, dismissible: true };

function buildDeps() {
  return { pushToast: { success: vi.fn(), info: vi.fn(), warning: vi.fn(), error: vi.fn() } };
}

function shownLevels(deps: ReturnType<typeof buildDeps>) {
  return LEVELS.filter((level) => deps.pushToast[level].mock.calls.length > 0);
}

describe('showSystemNotificationToast', () => {
  it.each(LEVELS)('shows a notification declared as %s with that toast level', (level) => {
    const deps = buildDeps();

    showSystemNotificationToast('Title', 'Body', { level }, deps);

    expect(shownLevels(deps)).toEqual([level]);
    expect(deps.pushToast[level]).toHaveBeenCalledWith('Title', TOAST_OPTIONS);
  });

  it('treats a notification without a level as a success', () => {
    const deps = buildDeps();

    showSystemNotificationToast('Title', 'Body', {}, deps);

    expect(shownLevels(deps)).toEqual(['success']);
    expect(deps.pushToast.success).toHaveBeenCalledWith('Title', TOAST_OPTIONS);
  });

  it.each(['critical', '', 3, null])('treats the unknown level %j as a success', (level) => {
    const deps = buildDeps();

    showSystemNotificationToast('Title', 'Body', { level }, deps);

    expect(shownLevels(deps)).toEqual(['success']);
  });

  it('leaves a snapshot-created notification to the chat window', () => {
    const deps = buildDeps();

    showSystemNotificationToast('Title', 'Body', { type: 'snapshot_created', level: 'error' }, deps);

    expect(shownLevels(deps)).toEqual([]);
  });
});
