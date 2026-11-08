/**
 * [INPUT] 无 (POS: 纯函数, 不依赖 React 与外部服务)
 * [OUTPUT] formatCognitiveUpdatedAt: ISO 时间 → 本地化的“日期 + 时间”(解析失败时原样返回); maintainSkippedBadgeLabel: 维护被跳过的原因 → 徽标文案
 * [POS] 统计卡与徽标共用的展示格式化。
 */

export function formatCognitiveUpdatedAt(iso: string | null | undefined, locale: string): string {
  if (!iso) {
    return '';
  }
  const parsed = Date.parse(iso);
  if (Number.isNaN(parsed)) {
    return iso;
  }
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(parsed);
}

export function maintainSkippedBadgeLabel(reason: string, translate: (key: string) => string): string {
  if (reason === 'compile_in_progress') {
    return translate('stats.lastMaintainSkippedCompile');
  }
  return translate('stats.lastMaintainSkipped');
}
