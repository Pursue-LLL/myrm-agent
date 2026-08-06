/**
 * @vitest-environment node
 */
import { describe, expect, it } from 'vitest';
import {
  resolveClipNotifyPayload,
  shouldStoreClipNotifyDeepLink,
} from '../../../../../myrm-agent-extension/src/wiki/clip_notify_payload.js';

const t = (key: string) => `__${key}__`;

describe('resolveClipNotifyPayload', () => {
  it('success uses linked body copy', () => {
    const payload = resolveClipNotifyPayload('success', { openUrl: 'http://x' }, t);
    expect(payload.titleKey).toBe('notifyClipSuccessTitle');
    expect(payload.body).toBe('__notifyClipSuccessBody__');
  });

  it('success_no_origin uses degraded hint', () => {
    const payload = resolveClipNotifyPayload('success_no_origin', {}, t);
    expect(payload.body).toBe('__clipSavedWithoutOrigin__');
  });

  it('duplicate picks NoLink body when openUrl empty', () => {
    const payload = resolveClipNotifyPayload('duplicate', { openUrl: '' }, t);
    expect(payload.body).toBe('__notifyClipDuplicateBodyNoLink__');
  });

  it('duplicate picks linked body when openUrl present', () => {
    const payload = resolveClipNotifyPayload(
      'duplicate',
      { openUrl: 'http://localhost:3000/settings/wiki' },
      t,
    );
    expect(payload.body).toBe('__notifyClipDuplicateBody__');
  });

  it('security picks NoLink body when openUrl empty', () => {
    const payload = resolveClipNotifyPayload('security', {}, t);
    expect(payload.body).toBe('__notifyClipSecurityBodyNoLink__');
  });

  it('error falls back to translate errClipFailed', () => {
    const payload = resolveClipNotifyPayload('error', { errorMessage: '   ' }, t);
    expect(payload.titleKey).toBe('notifyClipErrorTitle');
    expect(payload.body).toBe('__errClipFailed__');
  });

  it('error uses explicit message when provided', () => {
    const payload = resolveClipNotifyPayload('error', { errorMessage: 'network down' }, t);
    expect(payload.body).toBe('network down');
  });
});

describe('shouldStoreClipNotifyDeepLink', () => {
  it('returns false for empty urls', () => {
    expect(shouldStoreClipNotifyDeepLink('')).toBe(false);
    expect(shouldStoreClipNotifyDeepLink('   ')).toBe(false);
  });

  it('returns true for non-empty urls', () => {
    expect(shouldStoreClipNotifyDeepLink('http://localhost:3000/settings/wiki')).toBe(true);
  });
});
