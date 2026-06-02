/**
 * 格式化 token 数量
 */
export function formatTokens(tokens: number | undefined): string {
  if (!tokens) return '';
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(0)}M`;
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(0)}K`;
  return tokens.toString();
}

/**
 * 格式化价格为每百万 token 的美元价格
 * models.dev API 返回的价格已经是每百万 token 的价格
 * @param pricePerMillion - 每百万 token 的价格（美元），undefined 表示无数据
 * @returns 格式化后的价格字符串，显示为 "/M" 表示每百万 token；无数据返回 '-'
 */
export function formatPrice(pricePerMillion: number | undefined): string {
  if (pricePerMillion == null) return '-';
  if (pricePerMillion === 0) return '$0/M';
  if (pricePerMillion < 0.001) return `$${pricePerMillion.toFixed(4)}/M`;
  if (pricePerMillion < 0.01) return `$${pricePerMillion.toFixed(3)}/M`;
  if (pricePerMillion < 1) return `$${pricePerMillion.toFixed(2)}/M`;
  if (pricePerMillion < 10) return `$${pricePerMillion.toFixed(1)}/M`;
  return `$${Math.round(pricePerMillion)}/M`;
}
