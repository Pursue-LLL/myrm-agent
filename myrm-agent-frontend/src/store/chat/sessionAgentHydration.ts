/**
 * Session agent hydration invariant SSOT.
 *
 * Defines when store agent binding + security preset are considered ready for
 * user/E2E probes. Callers: loadMessages gate, chatAgentSessionRestore, tests.
 */

import type { AgentConfig, SecurityPreset } from '@/store/chat/types';
import { normalizeSecurityPreset } from '@/store/chat/securityPreset';

export interface AgentHydrationSnapshot {
  chatId?: string;
  agentConfig?: AgentConfig | null;
  securityPreset: SecurityPreset;
  isMessagesLoaded?: boolean;
  loading?: boolean;
  notFound?: boolean;
  loadError?: boolean;
}

export function shouldDeferMessagesReadyUntilAgentRestore(
  agentId: string | null | undefined,
): boolean {
  return Boolean(agentId?.trim());
}

export function expectedSecurityPresetForAgent(
  agentConfig: AgentConfig | null | undefined,
): SecurityPreset {
  return normalizeSecurityPreset(agentConfig?.defaultSecurityPreset);
}

export function securityPresetNeedsSync(
  currentPreset: SecurityPreset,
  agentConfig: AgentConfig | null | undefined,
): boolean {
  return currentPreset !== expectedSecurityPresetForAgent(agentConfig);
}

export function isAgentSessionHydrated(
  snapshot: AgentHydrationSnapshot,
  expectedAgentId: string,
  expectedPreset?: SecurityPreset,
): boolean {
  const boundAgentId = snapshot.agentConfig?.agentId ?? null;
  const preset = expectedPreset ?? expectedSecurityPresetForAgent(snapshot.agentConfig);
  return (
    snapshot.chatId !== undefined &&
    boundAgentId === expectedAgentId &&
    snapshot.securityPreset === preset &&
    snapshot.isMessagesLoaded === true &&
    snapshot.loading !== true &&
    snapshot.notFound !== true &&
    snapshot.loadError !== true
  );
}
