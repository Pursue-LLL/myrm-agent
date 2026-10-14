import { describe, expect, it, vi } from 'vitest';

import de from '../../../locales/de.json';
import en from '../../../locales/en.json';
import ja from '../../../locales/ja.json';
import ko from '../../../locales/ko.json';
import zhTW from '../../../locales/zh-TW.json';
import zh from '../../../locales/zh.json';

// The global test setup replaces next-intl, so the real formatter is loaded explicitly.
const { createTranslator } = await vi.importActual<typeof import('next-intl')>('next-intl');

const locales = { en, zh, 'zh-TW': zhTW, ja, ko, de } as const;

type Values = Record<string, string | number>;

/**
 * Toast copy resolved outside React components (stores, libs) or with values. The values mirror the real call
 * sites: a renamed placeholder would render the raw `{name}` for users, and no other check sees that.
 */
const WITH_VALUES: ReadonlyArray<readonly [string, Values]> = [
  ['chat.cacheResetNotice', { reason: 'reason-x', tokens: 7 }],
  ['chat.pdfParsedPages', { fileName: 'report.pdf', parsed: 3, total: 9 }],
  ['chat.pdfImageOptimized', { kept: 3, dropped: 8 }],
  ['chat.folderDrop.grantFailed', { path: '/data/projects' }],
  ['settings.sshVault.probeFailed', { host: 'host-x', message: 'message-x' }],
  ['settings.securityPolicy.profile.activated', { name: 'profile-x' }],
  ['settings.securityPolicy.privacy.routing.testSuccessLatency', { latency: 42 }],
  ['settings.wiki.reviewSlip.applied', { committed: 4, discarded: 6 }],
  ['settings.skills.detail.securityReviewNote', { recommendation: 'recommendation-x' }],
  ['agent.openapi.presetAdded', { name: 'preset-x' }],
  ['agent.configPanel.forcePushSummary', { version: 8, synced: 3, skipped: 5, failed: 2, total: 10 }],
  ['channels.dataPlane.deletedCount', { count: 1 }],
  ['channels.dataPlane.deletedCount', { count: 5 }],
  ['memory.shareRules.exported', { count: 1 }],
  ['memory.shareRules.exported', { count: 5 }],
  ['memory.shareRules.copied', { count: 1 }],
  ['memory.shareRules.copied', { count: 5 }],
  ['notifications.healthAlertTip', { tip: 'tip-x' }],
  ['notifications.budgetRemaining', { dimension: 'dimension-x', remaining: '0.1234' }],
  ['notifications.subagentStaleDescription', { minutes: 3, tokens: 25 }],
  ['notifications.subagentStaleStats', { minutes: 3, tokens: 25 }],
];

const WITHOUT_VALUES = [
  'agent.configEditor.goToSettings',
  'common.apiErrorDetails',
  'common.apiErrorTraceId',
  'common.errorTitle',
  'common.retry',
  'common.unknownError',
  'common.clipboard.copied',
  'common.clipboard.copyFailed',
  'common.clipboard.readBlocked',
  'common.clipboard.readRefused',
  'common.clipboard.readFailed',
  'notifications.agentProfileRollbackSuccess',
  'Goal.subgoalAddFailed',
  'Goal.subgoalRemoveNetworkError',
  'settings.skills.permissions.approveFailed',
  'settings.skills.detail.forceEnableFailed',
] as const;

describe.each(Object.entries(locales))('toast copy keys in %s', (locale, messages) => {
  const translator = createTranslator({ locale, messages });

  it.each(WITH_VALUES)('formats %s with the values the call site passes', (key, values) => {
    const text = translator(key as never, values as never);

    expect(text, `${key} should resolve`).not.toBe(key);
    expect(text).not.toMatch(/[{}]/);
    for (const value of Object.values(values)) {
      expect(text, `${key} should render ${String(value)}`).toContain(String(value));
    }
  });

  it.each(WITHOUT_VALUES)('resolves %s', (key) => {
    const text = translator(key as never);

    expect(text.trim().length).toBeGreaterThan(0);
    expect(text).not.toBe(key);
  });

  it('drops the uncached-token clause from the cache reset notice when nothing was uncached', () => {
    const withTokens = translator('chat.cacheResetNotice' as never, { reason: 'reason-x', tokens: 7 } as never);
    const withoutTokens = translator('chat.cacheResetNotice' as never, { reason: 'reason-x', tokens: 0 } as never);

    expect(withoutTokens).toContain('reason-x');
    expect(withoutTokens).not.toMatch(/[{}]/);
    expect(withoutTokens.length).toBeLessThan(withTokens.length);
  });
});
