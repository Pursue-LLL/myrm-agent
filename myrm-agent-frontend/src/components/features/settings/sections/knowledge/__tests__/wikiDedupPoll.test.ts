import { describe, expect, it } from 'vitest';

import {
  DEDUP_POLL_INTERVAL_MS,
  DEDUP_POLL_MAX_ATTEMPTS,
  isDedupScanTerminalPhase,
  shouldNotifyDedupScanFailedOnMount,
  shouldResumeDedupPoll,
} from '../wikiDedupPoll';

describe('wikiDedupPoll', () => {
  it('exports poll tuning constants', () => {
    expect(DEDUP_POLL_INTERVAL_MS).toBe(500);
    expect(DEDUP_POLL_MAX_ATTEMPTS).toBe(120);
  });

  it('detects terminal scan phases', () => {
    expect(isDedupScanTerminalPhase('done')).toBe(true);
    expect(isDedupScanTerminalPhase('failed')).toBe(true);
    expect(isDedupScanTerminalPhase('idle')).toBe(true);
    expect(isDedupScanTerminalPhase('scanning')).toBe(false);
    expect(isDedupScanTerminalPhase('grouping')).toBe(false);
  });

  it('detects active scan phases for resume polling', () => {
    expect(shouldResumeDedupPoll('scanning')).toBe(true);
    expect(shouldResumeDedupPoll('grouping')).toBe(true);
    expect(shouldResumeDedupPoll('done')).toBe(false);
    expect(shouldResumeDedupPoll('idle')).toBe(false);
  });

  it('detects failed phase that needs mount notification', () => {
    expect(shouldNotifyDedupScanFailedOnMount('failed')).toBe(true);
    expect(shouldNotifyDedupScanFailedOnMount('done')).toBe(false);
    expect(shouldNotifyDedupScanFailedOnMount('scanning')).toBe(false);
  });
});
