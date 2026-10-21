/**
 * [INPUT]
 * - next-intl::useTranslations (POS: 前端国际化 Hook，仅用其类型)
 * - @/services/statistics::GrowthDashboardData (POS: 成长看板数据契约)
 *
 * [OUTPUT]
 * - growthMarkdownLabels: 成长报告导出文案，取自 growthDashboard 命名空间
 * - buildGrowthMarkdown: 成长报告 Markdown 构建，技能排名只含已判定的技能
 * - downloadGrowthMarkdown: 触发 Markdown 文件下载
 *
 * [POS]
 * 成长进化中心报告导出。文案经 growthMarkdownLabels 注入，构建函数本身是纯函数，可脱离 React 测试。
 */
import type { useTranslations } from 'next-intl';
import type { GrowthDashboardData } from '@/services/statistics';

export interface GrowthMarkdownLabels {
  title: string;
  period: string;
  memories: string;
  memoryCitations: string;
  conversations: string;
  messages: string;
  cronJobs: string;
  toolCalls: string;
  savings: string;
  totalCost: string;
  skillHealth: string;
  /** Localized verdict of a health status. */
  skillStatus: (status: string) => string;
  skillRow: (name: string, score: number, statusLabel: string, calls7d: number | string) => string;
  generatedAt: string;
}

function formatDate(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Export wording from the `growthDashboard` namespace; a status this build has no wording for reads as a dash. */
export function growthMarkdownLabels(t: ReturnType<typeof useTranslations<'growthDashboard'>>): GrowthMarkdownLabels {
  return {
    title: t('export.title'),
    period: t('weeklySummary.title'),
    memories: t('snapshot.totalMemories'),
    memoryCitations: t('export.memoryCitations'),
    conversations: t('weeklySummary.conversations'),
    messages: t('weeklySummary.messages'),
    cronJobs: t('weeklySummary.cronExecutions'),
    toolCalls: t('weeklySummary.toolCalls'),
    savings: t('savings.title'),
    totalCost: t('savings.totalCost'),
    skillHealth: t('skillHealth.title'),
    skillStatus: (status) => (t.has(`skillHealth.status.${status}`) ? t(`skillHealth.status.${status}`) : '–'),
    skillRow: (name, score, statusLabel, calls7d) =>
      t('export.skillRow', { name, score: Math.round(score), status: statusLabel, calls7d }),
    generatedAt: t('export.generatedAt', { date: formatDate() }),
  };
}

export function buildGrowthMarkdown(data: GrowthDashboardData, labels: GrowthMarkdownLabels): string {
  const { snapshot, weekly_summary, cost_summary, skill_health } = data;
  const lines: string[] = [
    `# ${labels.title} (${formatDate()})`,
    '',
    `## ${labels.period}`,
    `- ${labels.conversations}: ${weekly_summary.conversations}`,
    `- ${labels.messages}: ${weekly_summary.messages_sent}`,
    `- ${labels.cronJobs}: ${weekly_summary.cron_executions}`,
    `- ${labels.toolCalls}: ${weekly_summary.tool_calls}`,
    '',
    `## ${labels.memories}`,
    `- ${labels.memories}: ${snapshot.total_memories}`,
    `- ${labels.memoryCitations}: ${snapshot.memory_citations_7d}`,
  ];

  if (cost_summary) {
    lines.push(
      '',
      `## ${labels.savings}`,
      `- ${labels.savings}: $${cost_summary.total_savings_usd.toFixed(2)}`,
      `- ${labels.totalCost}: $${cost_summary.total_cost_usd.toFixed(2)}`,
    );
  }

  // An unproven skill's score only measures how little evidence exists, so it takes no part in the ranking.
  const rankedSkills = skill_health
    .filter((skill) => skill.status !== 'UNPROVEN')
    .sort((a, b) => b.health_score - a.health_score)
    .slice(0, 10);

  if (rankedSkills.length > 0) {
    lines.push('', `## ${labels.skillHealth}`);
    for (const skill of rankedSkills) {
      const calls7d = skill.truncated ? `${skill.call_count_7d}+` : skill.call_count_7d;
      lines.push(labels.skillRow(skill.skill_name, skill.health_score, labels.skillStatus(skill.status), calls7d));
    }
  }

  lines.push('', `---`, labels.generatedAt);
  return lines.join('\n');
}

export function downloadGrowthMarkdown(content: string, filenamePrefix = 'myrm-journey'): void {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${filenamePrefix}-${formatDate()}.md`;
  anchor.click();
  URL.revokeObjectURL(url);
}
