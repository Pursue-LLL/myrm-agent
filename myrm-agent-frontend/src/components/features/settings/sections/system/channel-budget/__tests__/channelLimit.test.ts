/**
 * [INPUT]
 * - ../channelLimit (POS: Range of a channel's daily limit)
 *
 * [OUTPUT]
 * - Test suite for the range check of a channel's daily limit
 *
 * [POS]
 * Pins that both ends of the range are limits, and that what an emptied or runaway box parses to is not.
 */
import { describe, expect, it } from 'vitest';
import { CHANNEL_LIMIT_MAX_USD, CHANNEL_LIMIT_MIN_USD, isChannelLimitInRange } from '../channelLimit';

describe('isChannelLimitInRange', () => {
  it.each([CHANNEL_LIMIT_MIN_USD, 2, 7.25, CHANNEL_LIMIT_MAX_USD])('takes %s', (limit) => {
    expect(isChannelLimitInRange(limit)).toBe(true);
  });

  it.each([0, 0.009, -1, 10000.01, NaN, Infinity, -Infinity])('refuses %s', (limit) => {
    expect(isChannelLimitInRange(limit)).toBe(false);
  });
});
