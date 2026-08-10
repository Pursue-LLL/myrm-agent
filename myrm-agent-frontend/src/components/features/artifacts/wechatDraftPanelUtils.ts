import type { WeChatComplianceHit } from '@/services/channels';

export type WeChatComplianceSeverity = 'blocked' | 'warning';

export function normalizeWeChatComplianceHits(items: unknown): WeChatComplianceHit[] {
  if (!Array.isArray(items)) {
    return [];
  }
  const hits: WeChatComplianceHit[] = [];
  for (const item of items) {
    if (!item || typeof item !== 'object') {
      continue;
    }
    const record = item as Record<string, unknown>;
    const terms = Array.isArray(record.terms)
      ? record.terms.filter((term): term is string => typeof term === 'string')
      : [];
    if (typeof record.category !== 'string' || typeof record.label !== 'string') {
      continue;
    }
    hits.push({
      category: record.category,
      label: record.label,
      terms,
      highRisk: record.highRisk === true,
    });
  }
  return hits;
}

export function parseWeChatComplianceHits(data: Record<string, unknown> | undefined): WeChatComplianceHit[] {
  if (!data || !Array.isArray(data.hits)) {
    return [];
  }
  return normalizeWeChatComplianceHits(data.hits);
}

export const WECHAT_MAX_AUTHOR_LEN = 8;
export const WECHAT_MAX_DIGEST_LEN = 120;

export function clampWechatAuthor(value: string): string {
  return value.trim().slice(0, WECHAT_MAX_AUTHOR_LEN);
}

export function clampWechatDigest(value: string): string {
  return value.trim().slice(0, WECHAT_MAX_DIGEST_LEN);
}

export function resolveDefaultWechatDraftTitle(filename: string): string {
  const base = filename.replace(/\.(wechat\.)?html?$/i, '').trim();
  return base || filename;
}

export function resolveDefaultWechatAuthor(agentName?: string | null, presetName?: string | null): string {
  const agent = (agentName ?? '').trim();
  if (agent) {
    return clampWechatAuthor(agent);
  }
  return clampWechatAuthor(presetName ?? '');
}
