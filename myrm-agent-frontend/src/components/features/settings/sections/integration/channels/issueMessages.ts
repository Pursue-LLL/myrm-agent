/**
 * Channel diagnostics text mapping for the channel overview.
 *
 * [INPUT] none (the English message and fix texts come from `collect_issues` of each server channel provider)
 * [OUTPUT] ISSUE_MESSAGE_PATTERNS / ISSUE_FIX_PATTERNS: ordered pattern tables onto `channels.issues` keys;
 *          resolveIssueKey: first-match lookup that tells the caller which key (and which remaining text) to show
 * [POS] Pure lookup half of the issue translator, kept apart from the component so the pairing between server
 *       message texts and locale keys can be pinned by unit tests.
 */

export type IssuePattern = [pattern: RegExp, key: string, prefixOnly?: boolean];

export interface ResolvedIssueKey {
  key: string;
  /** Text that followed a prefix-only pattern; null when the whole message is replaced by the key's text. */
  rest: string | null;
}

// The first matching pattern wins, so a specific pattern must precede a general one that also matches it: a
// webhook setup failure also says "degraded mode".
export const ISSUE_MESSAGE_PATTERNS: IssuePattern[] = [
  [/not configured/i, 'notConfigured'],
  [/missing (configuration|credentials)/i, 'missingCredentials'],
  [/rejected the bot token/i, 'tokenRejected'],
  [/bot api could not be reached/i, 'apiUnreachable'],
  [/authentication failed/i, 'authFailed'],
  [/webhook.*(setup|set up) failed/i, 'webhookFailed'],
  [/degraded (state|mode)/i, 'degradedMode'],
  [/(error state|in ERROR)/i, 'errorState'],
  [/must use HTTPS/i, 'webhookHttps'],
  [/SDK.*not installed/i, 'sdkNotInstalled'],
  [/mautrix not installed/i, 'msgMautrixMissing'],
  [/lark-oapi not installed/i, 'msgLarkMissing'],
  [/SILK decoder.*not installed/i, 'msgWechatSilkMissing'],
  [/Run: uv sync/i, 'msgUvSyncRequired'],
  [/token.*failed/i, 'tokenFailed'],
  [/connection failed/i, 'connectionFailed'],
  [/encryption not configured/i, 'encryptionNotConfigured'],
  [/not logged in/i, 'notLoggedIn'],
  [/^last error:\s*/i, 'lastError', true],
];

export const ISSUE_FIX_PATTERNS: IssuePattern[] = [
  [/configure in settings/i, 'fixConfigureInSettings'],
  [/copy the token from botfather/i, 'fixReenterBotToken'],
  [/check the network and the proxy/i, 'fixCheckNetworkAndProxy'],
  [/verify.*valid.*permissions/i, 'fixCheckCredentials'],
  [/verify.*(token|password|secret)/i, 'fixVerifyToken'],
  [/scan QR code to login/i, 'fixScanQrCode'],
];

export function resolveIssueKey(text: string, patterns: IssuePattern[]): ResolvedIssueKey | null {
  for (const [pattern, key, prefixOnly] of patterns) {
    if (pattern.test(text)) {
      return { key, rest: prefixOnly ? text.replace(pattern, '').trim() : null };
    }
  }
  return null;
}
