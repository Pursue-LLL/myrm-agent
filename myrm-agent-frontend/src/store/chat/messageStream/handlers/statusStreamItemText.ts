/**
 * [INPUT]
 * - harness STATUS `data` of `context_compaction` (POS: compaction progress; `elapsed_s` comes with compaction inside a
 *   turn, the pre-reply gate reports the phase alone)
 * - harness STATUS `data` of the MoA overlay steps (POS: `trigger_reason` / `reason` say why the overlay ran or stood
 *   down)
 *
 * [OUTPUT]
 * - formatCompactionItemText(): detail of a `context_compaction` step: the elapsed seconds while it runs or after a
 *   timeout, the tokens saved once it completes
 * - formatMoaTriggerReason() / formatMoaSkipReason(): lead-in and reason shown on the MoA overlay steps
 *
 * [POS]
 * Detail wording of the STATUS progress steps that is derived from the event payload. A figure the event does not carry
 * is left out, never filled in.
 */

/** Lead-in of the MoA overlay step: why the overlay ran. */
export function formatMoaTriggerReason(reason: unknown): string {
  if (typeof reason !== 'string' || !reason) {
    return '';
  }
  switch (reason) {
    case 'consecutive_tool_failures':
      return '执行自适应协同 · ';
    case 'loop_guard_warning':
      return '循环优化协同 · ';
    case 'multi_tool_failures':
      return '多维诊断协同 · ';
    default:
      return '协同决策 · ';
  }
}

/** Reason shown when the MoA overlay stood down; a reason without wording is shown as sent. */
export function formatMoaSkipReason(reason: unknown): string {
  if (typeof reason !== 'string' || !reason) {
    return '';
  }
  switch (reason) {
    case 'risk_trigger_timeout':
      return '协同超时回退';
    case 'budget_pressure':
      return 'Token预算保护';
    case 'insufficient_refs':
      return '参考模型未就绪';
    default:
      return String(reason);
  }
}

/** Detail of a `context_compaction` step; only a figure the event carries is shown. */
export function formatCompactionItemText(data: Record<string, unknown>): string {
  switch (data.phase) {
    case 'active':
    case 'timeout':
      return typeof data.elapsed_s === 'number' ? `(${data.elapsed_s}s)` : '';
    case 'completed':
      // The saved tokens are read from this payload; the pre-reply gate sends them on the event itself, so its step
      // has no detail.
      return typeof data.tokens_saved === 'number' && data.tokens_saved > 0
        ? `(Tokens saved: ${data.tokens_saved})`
        : '';
    default:
      return '';
  }
}
