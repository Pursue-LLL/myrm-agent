/**
 * [OUTPUT]
 * - CHANNEL_LIMIT_MIN_USD / CHANNEL_LIMIT_MAX_USD: the range of a channel's daily limit, in USD
 * - isChannelLimitInRange: whether a parsed amount is a limit the server stores
 *
 * [POS]
 * The range of a channel's daily limit. The server enforces the same bounds on a stored policy and on the body that
 * creates one; the panel checks them before sending, so an amount the server would refuse is explained in the user's
 * language instead of coming back as a raw validation error.
 */

export const CHANNEL_LIMIT_MIN_USD = 0.01;
export const CHANNEL_LIMIT_MAX_USD = 10000;

/** Both bounds are stored. NaN, which an emptied box parses to, is in no range. */
export function isChannelLimitInRange(limit: number): boolean {
  return limit >= CHANNEL_LIMIT_MIN_USD && limit <= CHANNEL_LIMIT_MAX_USD;
}
