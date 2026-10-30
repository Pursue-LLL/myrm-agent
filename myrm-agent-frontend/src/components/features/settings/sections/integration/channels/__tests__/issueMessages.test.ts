import { describe, expect, it } from 'vitest';

import en from '../../../../../../../../locales/en.json';
import { ISSUE_FIX_PATTERNS, ISSUE_MESSAGE_PATTERNS, resolveIssueKey } from '../issueMessages';

describe('resolveIssueKey', () => {
  it.each([
    ['Channel in ERROR state; check credentials and network', 'errorState'],
    ['Channel running in degraded mode: polling keeps failing.', 'degradedMode'],
    ['Webhook URL must use HTTPS. Telegram rejects non-HTTPS URLs.', 'webhookHttps'],
  ])('maps the Telegram status message %j to %s', (message, key) => {
    expect(resolveIssueKey(message, ISSUE_MESSAGE_PATTERNS)).toEqual({ key, rest: null });
  });

  it('gives a webhook setup failure its own text rather than the generic degraded one', () => {
    expect(resolveIssueKey('Webhook setup failed. Channel running in degraded mode.', ISSUE_MESSAGE_PATTERNS)).toEqual({
      key: 'webhookFailed',
      rest: null,
    });
  });

  it('keeps the rest of a message when the pattern only names its prefix', () => {
    expect(resolveIssueKey('Last error: socket closed', ISSUE_MESSAGE_PATTERNS)).toEqual({
      key: 'lastError',
      rest: 'socket closed',
    });
  });

  it('returns null for a message no pattern knows, so the caller shows it as is', () => {
    expect(resolveIssueKey('Something nobody wrote a pattern for', ISSUE_MESSAGE_PATTERNS)).toBeNull();
  });

  it('maps fix hints with their own table', () => {
    expect(resolveIssueKey('Configure in Settings before use', ISSUE_FIX_PATTERNS)).toEqual({
      key: 'fixConfigureInSettings',
      rest: null,
    });
  });
});

describe('issue pattern tables', () => {
  const issueTexts = en.channels.issues as Record<string, string>;

  it.each([...ISSUE_MESSAGE_PATTERNS, ...ISSUE_FIX_PATTERNS].map(([, key]) => key))(
    'has a text for %s in channels.issues',
    (key) => {
      expect(typeof issueTexts[key]).toBe('string');
    },
  );
});
