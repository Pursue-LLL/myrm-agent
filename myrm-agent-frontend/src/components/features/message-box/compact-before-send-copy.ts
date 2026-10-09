/**
 * Copy, token formatting, and tooltip contracts for Compact-Before-Send token chip.
 *
 * Kept in a dedicated module to preserve fast refresh on composer message box components.
 */

export const COMPACT_BEFORE_SEND_COPY = {
  primarySendDefault: "Send",
  primarySendCompact: "Compact and send",
  chipCompactPrefix: "Compact",
  chipFullHistoryKept: "Full history kept",
  tooltipCompactWillTrigger: (tokensText: string) =>
    `Next send compacts ~${tokensText} tokens of history first. Click chip to keep full history.`,
  tooltipFullHistoryKept:
    "Keeping full history without preflight compaction. Click chip to restore auto-compact.",
  tooltipDefaultSend: "Send message",
} as const;

export function formatCompactChipTokens(tokens: number): string {
  if (tokens < 1000) {
    return String(tokens);
  }
  if (tokens < 1_000_000) {
    const val = tokens / 1000.0;
    return val < 10.0 ? `${val.toFixed(1)}k` : `${Math.round(val)}k`;
  }
  const val = tokens / 1_000_000.0;
  return val < 10.0 ? `${val.toFixed(1)}M` : `${Math.round(val)}M`;
}
