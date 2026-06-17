/**
 * [INPUT]
 * - services/runtime-health.ts::DoctorResponse, HealthReport, RepairAction (POS: 运行时健康API类型)
 * - lib/utils/clipboardUtils.ts::writeToClipboard (POS: Tauri/Web 双环境安全剪贴板封装)
 *
 * [OUTPUT]
 * - formatDoctorReportAsMarkdown: 将诊断数据格式化为 GitHub Issue 友好的 Markdown
 * - buildDiagnosticBundle: 组装完整的诊断 JSON（含客户端上下文）
 * - copyDiagnosticMarkdown: 复制 Markdown 到剪贴板
 * - downloadDiagnosticJson: 触发 JSON 文件下载
 *
 * [POS]
 * 诊断导出工具。将 DoctorDashboard 已有的 /doctor API 数据格式化为可分享的报告，
 * 供用户粘贴到 GitHub Issue 或附件上传，降低 bug 反馈门槛。
 */

import type { DoctorResponse, HealthReport, RepairAction } from '@/services/runtime-health';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';

interface ClientContext {
  userAgent: string;
  route: string;
  timestamp: string;
  locale: string;
  screenSize: string;
}

interface DiagnosticBundle {
  version: 1;
  generated_at: string;
  client_context: ClientContext;
  doctor: DoctorResponse;
}

function collectClientContext(): ClientContext {
  return {
    userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : 'unknown',
    route: typeof window !== 'undefined' ? window.location.pathname : 'unknown',
    timestamp: new Date().toISOString(),
    locale: typeof navigator !== 'undefined' ? navigator.language : 'unknown',
    screenSize:
      typeof window !== 'undefined' ? `${window.innerWidth}x${window.innerHeight}` : 'unknown',
  };
}

function statusEmoji(status: string): string {
  if (status === 'pass') return '\u2705';
  if (status === 'warn') return '\u26a0\ufe0f';
  return '\u274c';
}

function formatReportGroup(reports: HealthReport[], layerName: string): string {
  if (reports.length === 0) return '';

  const passCount = reports.filter((r) => r.status === 'pass').length;
  const lines = [`### ${layerName} (${passCount}/${reports.length} healthy)\n`];

  for (const r of reports) {
    lines.push(`- ${statusEmoji(r.status)} **${r.component_name}** — ${r.message}`);
    if (r.detail) lines.push(`  - \`${r.detail}\``);
    if (r.fix_suggestion) lines.push(`  - Fix: ${r.fix_suggestion}`);
  }

  return lines.join('\n');
}

function formatRepairActions(actions: RepairAction[]): string {
  if (actions.length === 0) return '';

  const lines = ['### Repair Actions\n'];
  for (const a of actions) {
    const riskBadge = a.risk_level === 'high' ? '[HIGH]' : a.risk_level === 'medium' ? '[MED]' : '[LOW]';
    lines.push(`- ${riskBadge} **${a.title}** (${a.component})`);
    lines.push(`  - Reason: ${a.reason}`);
    lines.push(`  - Expected: ${a.expected_effect}`);
  }
  return lines.join('\n');
}

export function formatDoctorReportAsMarkdown(data: DoctorResponse): string {
  const ctx = collectClientContext();
  const allReports = [...(data.harness || []), ...(data.server || [])];
  const passCount = allReports.filter((r) => r.status === 'pass').length;
  const failCount = allReports.filter((r) => r.status === 'fail').length;
  const warnCount = allReports.filter((r) => r.status === 'warn').length;
  const score = allReports.length > 0 ? Math.round((passCount / allReports.length) * 100) : 100;

  const sections = [
    `## Myrm System Diagnostic Report\n`,
    `**Health Score:** ${score}% | **Pass:** ${passCount} | **Fail:** ${failCount} | **Warn:** ${warnCount}`,
    `**Time:** ${ctx.timestamp} | **Route:** ${ctx.route}`,
    `**UA:** \`${ctx.userAgent}\`\n`,
    formatReportGroup(data.harness || [], 'Harness Framework Layer'),
    formatReportGroup(data.server || [], 'Server Business Layer'),
    formatRepairActions(data.repair_actions || []),
  ];

  return sections.filter(Boolean).join('\n\n');
}

export function buildDiagnosticBundle(data: DoctorResponse): DiagnosticBundle {
  return {
    version: 1,
    generated_at: new Date().toISOString(),
    client_context: collectClientContext(),
    doctor: data,
  };
}

export async function copyDiagnosticMarkdown(data: DoctorResponse): Promise<boolean> {
  const markdown = formatDoctorReportAsMarkdown(data);
  return writeToClipboard(markdown, true);
}

export function downloadDiagnosticJson(data: DoctorResponse): void {
  const bundle = buildDiagnosticBundle(data);
  const json = JSON.stringify(bundle, null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `myrm-diagnostic-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.json`;
  a.click();
  URL.revokeObjectURL(url);
}
