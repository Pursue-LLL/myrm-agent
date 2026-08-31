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
  skillRow: (name: string, score: number, status: string, calls7d: number) => string;
  generatedAt: string;
}

function formatDate(): string {
  return new Date().toISOString().slice(0, 10);
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

  const rankedSkills = [...skill_health]
    .sort((a, b) => b.health_score - a.health_score)
    .slice(0, 10);

  if (rankedSkills.length > 0) {
    lines.push('', `## ${labels.skillHealth}`);
    for (const skill of rankedSkills) {
      lines.push(labels.skillRow(skill.skill_name, skill.health_score, skill.status, skill.call_count_7d));
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
