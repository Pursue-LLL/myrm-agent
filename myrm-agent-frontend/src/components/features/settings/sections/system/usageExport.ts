/**
 * [INPUT]
 * - services/statistics::{UsageStats, DailyUsage} (POS: 统计数据契约)
 *
 * [OUTPUT]
 * - getProviderFromModel: 根据模型名确定性推断 Provider
 * - formatSubCentCost: 高灵敏度子美分金额无损格式化
 * - generateUsageCsv: 导出纯文本 CSV 报告字符串
 * - downloadUsageCsv: 触发浏览器本地无损文件下载
 *
 * [POS]
 * src/components/features/settings/sections/system/usageExport.ts — 零额外 LLM 开销的纯确定性算力用量 CSV 导出器。
 */

import type { UsageStats, DailyUsage } from '@/services/statistics';

/**
 * 确定性规则推断模型所属的 Provider。
 */
export function getProviderFromModel(modelName: string): string {
  const lower = modelName.toLowerCase();
  if (lower.startsWith('gpt') || lower.startsWith('o1') || lower.startsWith('o3') || lower.includes('openai')) {
    return 'OpenAI';
  }
  if (lower.startsWith('claude') || lower.includes('anthropic')) {
    return 'Anthropic';
  }
  if (lower.startsWith('deepseek')) {
    return 'DeepSeek';
  }
  if (lower.startsWith('gemini')) {
    return 'Google';
  }
  if (lower.startsWith('qwen')) {
    return 'Qwen/Alibaba';
  }
  if (lower.startsWith('llama') || lower.includes('meta')) {
    return 'Meta';
  }
  if (lower.startsWith('ollama') || lower.startsWith('local')) {
    return 'Local/Ollama';
  }
  return 'Custom/Other';
}

/**
 * 高灵敏子美分金额格式化。
 * 彻底消除小于 $0.01 的费用被抹成 $0.00 的账单失真问题。
 */
export function formatSubCentCost(cost: number): string {
  if (cost === 0) return '0.00';
  if (cost < 0.01) {
    return cost.toFixed(4);
  }
  return cost.toFixed(2);
}

/**
 * 生成用量数据 CSV 纯文本字符串。
 */
export function generateUsageCsv(stats: UsageStats | null, daily: DailyUsage[]): string {
  const lines: string[] = [];

  // 1. 总体概览行
  lines.push('--- SUMMARY ---');
  lines.push('Total Calls,Total Tokens,Input Tokens,Output Tokens,Cached Tokens,Total Cost (USD),Cache Hit Rate (%)');
  if (stats) {
    lines.push(
      [
        stats.calls,
        stats.totalTokens,
        stats.inputTokens,
        stats.outputTokens,
        stats.cachedTokens,
        formatSubCentCost(stats.costUsd),
        stats.cacheHitRate.toFixed(2),
      ].join(','),
    );
  } else {
    lines.push('0,0,0,0,0,0.00,0.00');
  }

  lines.push('');

  // 2. 模型细粒度 breakdown 表
  lines.push('--- MODEL BREAKDOWN ---');
  lines.push('Model,Provider,Calls,Input Tokens,Output Tokens,Cached Tokens,Total Tokens,Cost (USD)');
  if (stats && stats.modelBreakdown) {
    for (const [modelName, m] of Object.entries(stats.modelBreakdown)) {
      const provider = getProviderFromModel(modelName);
      lines.push(
        [
          `"${modelName}"`,
          `"${provider}"`,
          m.calls,
          m.inputTokens,
          m.outputTokens,
          m.cachedTokens,
          m.totalTokens,
          formatSubCentCost(m.costUsd),
        ].join(','),
      );
    }
  }

  lines.push('');

  // 3. 每日用量历史明细
  lines.push('--- DAILY HISTORY ---');
  lines.push('Date,Calls,Total Tokens,Input Tokens,Output Tokens,Cached Tokens,Cost (USD)');
  if (daily && daily.length > 0) {
    for (const d of daily) {
      lines.push(
        [
          d.date,
          d.calls,
          d.totalTokens,
          d.inputTokens,
          d.outputTokens,
          d.cachedTokens,
          formatSubCentCost(d.costUsd),
        ].join(','),
      );
    }
  }

  return lines.join('\n');
}

/**
 * 触发纯客户端确定性下载 CSV 文件。
 */
export function downloadUsageCsv(stats: UsageStats | null, daily: DailyUsage[]): void {
  const csvContent = generateUsageCsv(stats, daily);
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);

  const now = new Date();
  const dateStr = now.toISOString().split('T')[0];
  const filename = `myrm_usage_report_${dateStr}.csv`;

  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', filename);
  link.style.visibility = 'hidden';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
