/**
 * Product surface SSOT — hidden builtin agents mirrored from server product_surface.py.
 * `builtin-ko-office` is a retired preset: no spec ships any more, and the row an earlier version created stays hidden.
 */
export const HIDDEN_BUILTIN_AGENT_IDS = new Set(['builtin-researcher', 'builtin-deep-search', 'builtin-ko-office']);

export function isHiddenBuiltinAgent(agentId: string | null | undefined): boolean {
  if (!agentId) {
    return false;
  }
  return HIDDEN_BUILTIN_AGENT_IDS.has(agentId);
}

export function resolveVisibleBuiltinAgentId(agentId: string | null | undefined, fallback = 'builtin-general'): string {
  if (!agentId || isHiddenBuiltinAgent(agentId)) {
    return fallback;
  }
  return agentId;
}
