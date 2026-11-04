/**
 * Copy the product reads through a key it builds at run time must exist in every locale file.
 *
 * `verify:i18n-references` resolves only literal keys, and `verify:i18n` only compares the locale files with each
 * other, so a `t(variable)` whose value no locale holds shows the person the raw key path. Each family below
 * names the code that decides the key and checks every value it can take against all six locales.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { INTENSITY_LEVELS } from '@/components/features/chat-window/mobile/useMobileSheetEntries';
import { WEATHER_LABEL_KEYS } from '@/components/features/message-box/useContextWatermarkMetrics';
import { LANE_LABEL_CODES } from '@/components/features/settings/sections/knowledge/memory-migration-wizard/PreviewCards';
import { PREVIEW_BUCKET_CODES } from '@/components/features/settings/sections/knowledge/memory-migration-wizard/PreviewPanels';
import { KNOWN_PERMISSIONS } from '@/components/features/settings/sections/system/securityPolicyUtils';
import { locales } from '@/i18n/config';
import { resolveLockedUseDoctorBadgeKey, resolveLockedUseDoctorDetailKey } from '@/lib/desktop/desktopLockedUseDoctor';
import { deriveTaskDecisionFrame } from '@/lib/kanban/kanbanDecisionFrame';
import type { KanbanTask } from '@/services/kanban';
import type { HealthReport } from '@/services/runtime-health';
import { ARTIFACT_TYPES } from '@/store/chat/types/artifacts';

type Messages = { [key: string]: string | Messages };

const messagesByLocale = new Map<string, Messages>(
  locales.map((locale) => [
    locale,
    JSON.parse(readFileSync(join(process.cwd(), 'locales', `${locale}.json`), 'utf-8')) as Messages,
  ]),
);

function textAt(messages: Messages, path: string): string | undefined {
  let node: string | Messages | undefined = messages;
  for (const part of path.split('.')) {
    node = typeof node === 'object' ? node[part] : undefined;
  }
  return typeof node === 'string' ? node : undefined;
}

/** The `namespace.key` paths no locale file holds a non-empty text for, as `locale: path`. */
function missingTexts(namespace: string, keys: Iterable<string>): string[] {
  const missing: string[] = [];
  for (const [locale, messages] of messagesByLocale) {
    for (const key of keys) {
      if (!textAt(messages, `${namespace}.${key}`)?.trim()) {
        missing.push(`${locale}: ${namespace}.${key}`);
      }
    }
  }
  return missing;
}

function report(status: HealthReport['status'], code: string | null, metaData?: Record<string, unknown>): HealthReport {
  return { component_name: 'DesktopLockedUse', status, message: '', code, meta_data: metaData ?? null };
}

describe('dynamic translation key families', () => {
  it('security rule editor: every permission id has a label', () => {
    expect(missingTexts('settings.securityPolicy.permissionTypes', KNOWN_PERMISSIONS)).toEqual([]);
  });

  it('artifact card: every artifact type has a label', () => {
    expect(missingTexts('artifacts.types', ARTIFACT_TYPES)).toEqual([]);
  });

  it('context usage badge: every weather tier has a label', () => {
    expect(missingTexts('chat.contextUsage', Object.values(WEATHER_LABEL_KEYS))).toEqual([]);
  });

  it('desktop locked-use doctor: every badge and detail key it can return has a text', () => {
    const reports: Array<HealthReport | null> = [
      null,
      report('warn', 'WARN_CURTAIN_BRIDGE_MISSING'),
      report('fail', 'ERR_CURTAIN_BRIDGE_MISSING'),
      report('fail', 'ERR_DESKTOP_SHELL_UNAVAILABLE'),
      report('fail', 'ERR_SOMETHING_ELSE'),
      report('pass', 'OK_DESKTOP_LOCKED_USE_N_A'),
      report('pass', 'OK', { locked_use_enabled: true }),
      report('pass', 'OK', { locked_use_enabled: false }),
      report('pass', 'OK'),
    ];
    const keys = new Set<string>();
    for (const current of reports) {
      for (const isLoading of [true, false]) {
        keys.add(resolveLockedUseDoctorBadgeKey(current, isLoading));
      }
      const detail = resolveLockedUseDoctorDetailKey(current);
      if (detail !== null) {
        keys.add(detail);
      }
    }

    // Seven badge keys and five detail keys: a branch this matrix does not reach would go unchecked.
    expect(keys.size).toBe(12);
    expect(missingTexts('settings.desktopPermissions', keys)).toEqual([]);
  });

  it('kanban card: every recommended action the decision frame can pick has a text', () => {
    const taskIn = (status: string, overrides: Partial<KanbanTask> = {}): KanbanTask =>
      ({ status, metadata: {}, ...overrides }) as KanbanTask;
    const tasks = [
      taskIn('in_review'),
      taskIn('blocked', { block_kind: 'human' }),
      taskIn('blocked'),
      taskIn('failed'),
      taskIn('triage'),
      taskIn('running', { metadata: { completion_intent: true } }),
      taskIn('running'),
      taskIn('ready'),
      taskIn('backlog'),
      taskIn('completed'),
    ];
    const keys = new Set(tasks.map((task) => deriveTaskDecisionFrame(task).recommendedActionKey));

    // Ten statuses reach ten distinct actions: a branch this list does not reach would go unchecked.
    expect(keys.size).toBe(10);
    expect(missingTexts('kanban', keys)).toEqual([]);
  });

  it('mobile sheet: every thinking intensity level has a label', () => {
    expect(missingTexts('thinkingIntensity', INTENSITY_LEVELS)).toEqual([]);
  });

  it('background task row: every exit category the server classifies a shell task with has a label', () => {
    // The shell exit vocabulary of classify_background_exit (harness bash/_tool/background_listeners.py).
    expect(
      missingTexts('progressSteps.errorCategories', ['oom_killed', 'segfault', 'signal_terminated', 'nonzero_exit']),
    ).toEqual([]);
  });

  it('memory migration wizard: every preview bucket and lane title it localizes has a text', () => {
    expect(missingTexts('memory.migrationWizard.preview.previewBucket', PREVIEW_BUCKET_CODES)).toEqual([]);
    expect(missingTexts('memory.migrationWizard.preview.laneLabels', LANE_LABEL_CODES)).toEqual([]);
  });

  it('flags a key a locale does not hold, so the checks above can fail', () => {
    expect(missingTexts('artifacts.types', ['no_such_type'])).toHaveLength(locales.length);
  });
});
