/**
 * [INPUT]
 * - BuiltinToolId catalog, sandbox deploy mode, CP entitlement flags
 *
 * [OUTPUT]
 * - stripEntitlementBlockedBuiltinTools: remove cron/computer_use/external_cli when sandbox blocks them
 *
 * [POS]
 * Aligns agent config editor state with server runtime gates (mirror BuiltinToolsPanel disabled rules).
 */
import type { BuiltinToolId } from '@/store/chat/types';

export interface EntitlementBlockedBuiltinToolsOptions {
  sandbox: boolean;
  canUseCron: boolean;
  canUseVnc: boolean;
}

export function stripEntitlementBlockedBuiltinTools(
  tools: readonly BuiltinToolId[],
  options: EntitlementBlockedBuiltinToolsOptions,
): BuiltinToolId[] {
  if (!options.sandbox) {
    return [...tools];
  }

  return tools.filter((id) => {
    if (id === 'external_cli') {
      return false;
    }
    if (id === 'cron' && !options.canUseCron) {
      return false;
    }
    if (id === 'computer_use' && !options.canUseVnc) {
      return false;
    }
    return true;
  });
}
