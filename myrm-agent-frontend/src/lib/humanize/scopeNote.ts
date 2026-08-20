import type { ScopeNote, TranslateFn } from './types';

const EXTERNAL_TOOLS = new Set(['send_message', 'send_message_tool', 'send_file', 'channel_send', 'deploy_approval']);

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

  const target = typeof toolInput.target === 'string' ? toolInput.target : '';
  if (EXTERNAL_TOOLS.has(toolName)) {
    const platform = platformLabelFromTarget(target);
    return {
      text: t('scope.external', { destination: platform || t('scope.external_unknown') }),
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
