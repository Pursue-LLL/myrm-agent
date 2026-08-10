export const WECHAT_ARTICLE_FORMATTER_SKILL = 'wechat-article-formatter';

const WEIXIN_ARTICLE_URL_PATTERN = /https?:\/\/(?:[\w-]+\.)*mp\.weixin\.qq\.com\/s\//i;

export function containsWeixinArticleUrl(text: string): boolean {
  return WEIXIN_ARTICLE_URL_PATTERN.test(text);
}

export function buildAgentSkillsSettingsHref(agentId?: string | null): string {
  if (agentId) {
    return `/settings/agents?agentId=${encodeURIComponent(agentId)}#loadout`;
  }
  return '/settings/agents#loadout';
}

export function isWechatArticleFormatterActive(params: {
  selectedSkillIds: string[];
  sessionSkillOverrides: string[] | null;
  formatterSkillIds: string[];
}): boolean {
  const { selectedSkillIds, sessionSkillOverrides, formatterSkillIds } = params;
  if (formatterSkillIds.length === 0) {
    return false;
  }
  const mountedFormatter = formatterSkillIds.some((id) => selectedSkillIds.includes(id));
  if (!mountedFormatter) {
    return false;
  }
  if (sessionSkillOverrides === null) {
    return true;
  }
  return sessionSkillOverrides.includes(WECHAT_ARTICLE_FORMATTER_SKILL);
}
