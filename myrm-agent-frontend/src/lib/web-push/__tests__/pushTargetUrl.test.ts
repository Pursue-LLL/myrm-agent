import { describe, expect, it } from 'vitest';

import {
  chatIdFromPushPath,
  resolvePushClientFocusAction,
  sanitizePushTargetUrl,
} from '../pushTargetUrl';

const ORIGIN = 'https://app.example.com';

describe('sanitizePushTargetUrl', () => {
  it('allows settings paths with query', () => {
    expect(sanitizePushTargetUrl('/settings/system?tab=alerts', ORIGIN)).toBe(
      '/settings/system?tab=alerts',
    );
  });

  it('allows chat paths with approval query', () => {
    expect(
      sanitizePushTargetUrl('/session-abcdef12?approval=ap-1', ORIGIN),
    ).toBe('/session-abcdef12?approval=ap-1');
  });

  it('rejects cross-origin URLs', () => {
    expect(sanitizePushTargetUrl('https://evil.example/phish', ORIGIN)).toBe('/');
  });

  it('rejects reserved top-level segments as chat links', () => {
    expect(sanitizePushTargetUrl('/settings', ORIGIN)).toBe('/');
  });

  it('rejects root and multi-segment paths', () => {
    expect(sanitizePushTargetUrl('/', ORIGIN)).toBe('/');
    expect(sanitizePushTargetUrl('/chat/foo/bar', ORIGIN)).toBe('/');
  });

  it('rejects short or invalid chat id segments', () => {
    expect(sanitizePushTargetUrl('/short1?approval=ap-1', ORIGIN)).toBe('/');
    expect(sanitizePushTargetUrl('/bad$id!!?approval=ap-1', ORIGIN)).toBe('/');
  });

  it('accepts absolute same-origin chat URLs', () => {
    expect(
      sanitizePushTargetUrl(
        'https://app.example.com/session-abcdef12?approval=ap-2',
        ORIGIN,
      ),
    ).toBe('/session-abcdef12?approval=ap-2');
  });

  it('falls back to home when URL parsing throws', () => {
    expect(sanitizePushTargetUrl('::::', ORIGIN)).toBe('/');
  });
});

describe('chatIdFromPushPath', () => {
  it('extracts a valid chat id', () => {
    expect(chatIdFromPushPath('/session-abcdef12')).toBe('session-abcdef12');
  });

  it('returns null for reserved segments', () => {
    expect(chatIdFromPushPath('/settings/system')).toBeNull();
  });
});

describe('resolvePushClientFocusAction', () => {
  it('focuses when pathname and query already match', () => {
    expect(
      resolvePushClientFocusAction(
        'https://app.example.com/session-abcdef12?approval=ap-1',
        '/session-abcdef12?approval=ap-1',
        ORIGIN,
      ),
    ).toBe('focus');
  });

  it('navigates when pathname matches but query differs', () => {
    expect(
      resolvePushClientFocusAction(
        'https://app.example.com/session-abcdef12',
        '/session-abcdef12?approval=ap-1',
        ORIGIN,
      ),
    ).toBe('navigate');
  });

  it('returns null when pathname differs', () => {
    expect(
      resolvePushClientFocusAction(
        'https://app.example.com/other-chat-99',
        '/session-abcdef12?approval=ap-1',
        ORIGIN,
      ),
    ).toBeNull();
  });

  it('returns null for malformed client or target URLs', () => {
    expect(resolvePushClientFocusAction('not-a-url', '/session-abcdef12', ORIGIN)).toBeNull();
    expect(
      resolvePushClientFocusAction(
        'https://app.example.com/session-abcdef12',
        '::::',
        ORIGIN,
      ),
    ).toBeNull();
  });

  it('navigates when query params differ even if pathname matches', () => {
    expect(
      resolvePushClientFocusAction(
        'https://app.example.com/session-abcdef12?approval=old',
        '/session-abcdef12?approval=new',
        ORIGIN,
      ),
    ).toBe('navigate');
  });
});
