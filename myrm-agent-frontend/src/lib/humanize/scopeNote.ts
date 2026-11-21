import { extractContextFromToolInput } from './extractContext';
import type { ScopeNote, TranslateFn } from './types';

/**
 * Tools that put data in front of someone else: the tools of the backend's socially irreversible set that exist
 * (`_IRREVERSIBLE_SOCIAL_TOOLS` in the harness `core/security/spend_governance.py`). Keep the two lists in step.
 */
const EXTERNAL_TOOLS = new Set(['channel_notify_tool', 'artifact_publish']);

export function platformLabelFromTarget(target: string): string {
  const platform = target.split(':')[0]?.toLowerCase() ?? '';
  const names: Record<string, string> = {
    slack: 'Slack',
    telegram: 'Telegram',
    discord: 'Discord',
  };
  return names[platform] ?? platform;
}

/** Plain-words scope note for approval cards. */
export function resolveScopeNote(toolName: string, toolInput: Record<string, unknown>, t: TranslateFn): ScopeNote {
  if (toolName === 'save_skill' || toolName === 'save_skill_tool') {
    return { text: t('scope.save_skill'), external: false };
  }
  if (toolName === 'skill_manage_tool') {
    const action = typeof toolInput.action === 'string' ? toolInput.action.trim() : '';
    if (action === 'save') {
      return { text: t('scope.save_skill'), external: false };
    }
  }

  if (EXTERNAL_TOOLS.has(toolName)) {
    // Only a notification names where it goes; an artifact's hosting target is an id the user cannot read.
    const destination =
      toolName === 'channel_notify_tool' ? extractContextFromToolInput(toolInput).destination : undefined;
    return {
      text: t('scope.external', { destination: destination ?? t('scope.external_unknown') }),
      external: true,
    };
  }

  if (toolName.startsWith('mcp__')) {
    return { text: t('scope.connector'), external: true };
  }

  const overwrite = toolInput.overwrite === true || toolInput.overwrite === 'true' || toolInput.overwrite === 1;
  if (overwrite) {
    return { text: t('scope.local_overwrite'), external: false };
  }

  return { text: t('scope.local'), external: false };
}
