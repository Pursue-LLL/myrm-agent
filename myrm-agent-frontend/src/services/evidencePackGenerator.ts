/**
 * [INPUT]
 * - services/statistics::ExecutionTrace, TraceToolCall, TraceError (POS: 运行轨迹元数据契约)
 * - lib/utils/fileUtils::sanitizeFilename, triggerDownload (POS: 安全下载工具)
 * - EvidencePackTranslator: 调用方传入 `evidencePack` 命名空间的 next-intl 翻译函数，本模块不依赖 React
 *
 * [OUTPUT]
 * - SixStepEvidencePack: 六步项目经验证据包数据契约
 * - generateEvidencePackFromTrace: 从 ExecutionTrace 组装六步证据包（文案按 translator 本地化）
 * - exportEvidencePackToMarkdown: 格式化为 Markdown 文档
 * - exportEvidencePackToJson: 格式化为 JSON 字符串
 * - downloadEvidencePack: 触发文件下载
 *
 * [POS]
 * 项目经验六步证据包提炼核心服务。将零散的执行轨迹收敛为结构化工程资产。
 */

import type { ExecutionTrace, TraceToolCall, TraceError, TraceOutcome } from '@/services/statistics';
import { sanitizeFilename, triggerDownload } from '@/lib/utils/fileUtils';

/** Translator bound to the `evidencePack` namespace. */
export interface EvidencePackTranslator {
  (key: string, values?: Record<string, string | number>): string;
}

export type EvidencePackStepId =
  'requirements' | 'architecture' | 'initial_impl' | 'execution_correction' | 'verification' | 'takeaways';

export interface EvidencePackStep {
  stepIndex: number;
  id: EvidencePackStepId;
  title: string;
  shortTitle: string;
  summary: string;
  details: string[];
  metrics?: Record<string, string | number>;
}

export interface SixStepEvidencePack {
  sessionId: string;
  generatedAt: string;
  taskTitle: string;
  outcome: TraceOutcome;
  totalDurationMs: number;
  totalTokens: number;
  totalToolCalls: number;
  steps: EvidencePackStep[];
}

const PLANNING_TOOL_KEYWORDS = ['task_planning', 'structure-planner', 'sequentialthinking', 'delegate_task'];
const EDIT_TOOL_KEYWORDS = ['file_write_tool', 'file_edit_tool', 'patch', 'write', 'str_replace'];
const VERIFICATION_TOOL_KEYWORDS = ['test', 'pytest', 'bash', 'audit', 'lint', 'verifier', 'check'];

function matchesAnyKeyword(toolName: string, keywords: readonly string[]): boolean {
  const lowered = toolName.toLowerCase();
  return keywords.some((keyword) => lowered.includes(keyword));
}

function buildRequirementDetails(trace: ExecutionTrace, t: EvidencePackTranslator): string[] {
  return [trace.task_input ? trace.task_input.trim() : t('noTextInput')];
}

function buildArchitectureDetails(trace: ExecutionTrace, t: EvidencePackTranslator): string[] {
  const planningCalls = trace.tool_calls.filter((call: TraceToolCall) =>
    matchesAnyKeyword(call.tool_name, PLANNING_TOOL_KEYWORDS),
  );
  if (planningCalls.length === 0) {
    return [t('directExecution')];
  }
  const details = [t('planningDetected', { count: planningCalls.length })];
  planningCalls.slice(0, 5).forEach((call) => {
    const summary =
      call.output_summary ||
      (call.input_data ? JSON.stringify(call.input_data).slice(0, 100) : t('planningNodeFallback'));
    details.push(`[${call.tool_name}] ${summary}`);
  });
  return details;
}

function buildInitialImplDetails(trace: ExecutionTrace, t: EvidencePackTranslator): string[] {
  const firstWrite = trace.tool_calls.find((call: TraceToolCall) =>
    matchesAnyKeyword(call.tool_name, EDIT_TOOL_KEYWORDS),
  );
  if (!firstWrite) {
    return [t('noFileChanges')];
  }
  const details = [t('firstWrite', { tool: firstWrite.tool_name, sequence: firstWrite.sequence })];
  if (firstWrite.input_data && typeof firstWrite.input_data === 'object') {
    const input = firstWrite.input_data as Record<string, unknown>;
    const pathValue = input.path || input.file_path;
    if (pathValue) {
      details.push(t('targetFile', { path: String(pathValue) }));
    }
  }
  return details;
}

function buildExecutionDetails(
  trace: ExecutionTrace,
  failedCalls: TraceToolCall[],
  t: EvidencePackTranslator,
): string[] {
  const details = [t('executionSummary', { total: trace.tool_calls.length, failed: failedCalls.length })];
  (trace.errors ?? []).slice(0, 3).forEach((err: TraceError) => {
    details.push(t('errorRecord', { type: err.error_type || 'Error', message: err.error.slice(0, 120) }));
  });
  failedCalls.slice(0, 3).forEach((call) => {
    details.push(t('selfHealPoint', { tool: call.tool_name }));
  });
  return details;
}

function buildVerificationDetails(trace: ExecutionTrace, t: EvidencePackTranslator): string[] {
  const testCalls = trace.tool_calls.filter((call: TraceToolCall) =>
    matchesAnyKeyword(call.tool_name, VERIFICATION_TOOL_KEYWORDS),
  );
  if (testCalls.length === 0) {
    return [t('verificationInferred')];
  }
  const passedCount = testCalls.filter((call) => call.success).length;
  const details = [
    t('verificationSummary', {
      count: testCalls.length,
      rate: ((passedCount / testCalls.length) * 100).toFixed(0),
    }),
  ];
  testCalls.slice(0, 3).forEach((call) => {
    details.push(
      t('verificationRun', { tool: call.tool_name, result: call.success ? t('resultPassed') : t('resultFailed') }),
    );
  });
  return details;
}

function buildTakeawayDetails(trace: ExecutionTrace, t: EvidencePackTranslator): string[] {
  if (trace.outcome === 'success') {
    return [t('takeawayClosedLoop'), t('takeawayExtractSkill')];
  }
  const details = [t('takeawayNotSuccess', { outcome: trace.outcome })];
  if (trace.first_irrecoverable_index != null) {
    details.push(t('takeawayFirstFatal', { index: trace.first_irrecoverable_index }));
  }
  return details;
}

/**
 * 从原始执行轨迹提炼六步项目经验证据包
 */
export function generateEvidencePackFromTrace(trace: ExecutionTrace, t: EvidencePackTranslator): SixStepEvidencePack {
  const taskTitle = trace.task_input ? trace.task_input.split('\n')[0].slice(0, 60) : t('untitledTask');
  const failedCalls = trace.tool_calls.filter((call: TraceToolCall) => !call.success || Boolean(call.error));

  const stepSpecs: ReadonlyArray<{
    id: EvidencePackStepId;
    details: string[];
    metrics?: Record<string, string | number>;
  }> = [
    { id: 'requirements', details: buildRequirementDetails(trace, t) },
    { id: 'architecture', details: buildArchitectureDetails(trace, t) },
    { id: 'initial_impl', details: buildInitialImplDetails(trace, t) },
    {
      id: 'execution_correction',
      details: buildExecutionDetails(trace, failedCalls, t),
      metrics: {
        [t('metricTotalCalls')]: trace.tool_calls.length,
        [t('metricFailures')]: failedCalls.length,
      },
    },
    { id: 'verification', details: buildVerificationDetails(trace, t) },
    { id: 'takeaways', details: buildTakeawayDetails(trace, t) },
  ];

  const steps: EvidencePackStep[] = stepSpecs.map((spec, index) => ({
    stepIndex: index + 1,
    id: spec.id,
    title: t(`steps.${spec.id}.title`),
    shortTitle: t(`steps.${spec.id}.shortTitle`),
    summary: t(`steps.${spec.id}.summary`),
    details: spec.details,
    metrics: spec.metrics,
  }));

  return {
    sessionId: trace.session_id,
    generatedAt: new Date().toISOString(),
    taskTitle,
    outcome: trace.outcome,
    totalDurationMs: trace.duration_ms,
    totalTokens: trace.total_tokens,
    totalToolCalls: trace.tool_calls.length,
    steps,
  };
}

/**
 * 导出为标准化 Markdown 报告
 */
export function exportEvidencePackToMarkdown(pack: SixStepEvidencePack, t: EvidencePackTranslator): string {
  const durationSec = (pack.totalDurationMs / 1000).toFixed(1);
  const lines: string[] = [
    `# ${t('markdownHeading', { title: pack.taskTitle })}`,
    '',
    `> **${t('markdownSessionId')}**: \`${pack.sessionId}\`  `,
    `> **${t('markdownOutcome')}**: \`${pack.outcome.toUpperCase()}\` | **${t('markdownDuration')}**: ${durationSec}s | **${t('markdownTokens')}**: ${pack.totalTokens.toLocaleString()} | **${t('markdownToolCalls')}**: ${pack.totalToolCalls}  `,
    `> **${t('markdownGeneratedAt')}**: ${pack.generatedAt}`,
    '',
    '---',
    '',
  ];

  pack.steps.forEach((step) => {
    lines.push(`## ${t('markdownStepHeading', { index: step.stepIndex, title: step.title })}`);
    lines.push(`*${step.summary}*`);
    lines.push('');
    step.details.forEach((item) => {
      lines.push(`- ${item}`);
    });
    if (step.metrics) {
      lines.push('');
      lines.push(`**${t('markdownMetrics')}**:`);
      Object.entries(step.metrics).forEach(([k, v]) => {
        lines.push(`- ${k}: \`${v}\``);
      });
    }
    lines.push('');
  });

  lines.push('---');
  lines.push(`*${t('markdownFooter')}*`);
  return lines.join('\n');
}

/**
 * 导出为结构化 JSON
 */
export function exportEvidencePackToJson(pack: SixStepEvidencePack): string {
  return JSON.stringify(pack, null, 2);
}

/**
 * 触发文件下载
 */
export function downloadEvidencePack(
  pack: SixStepEvidencePack,
  format: 'markdown' | 'json',
  t: EvidencePackTranslator,
): void {
  const dateStr = new Date().toISOString().slice(0, 10);
  const baseName = sanitizeFilename(`EvidencePack_${pack.taskTitle.slice(0, 20)}_${dateStr}`);

  if (format === 'markdown') {
    const blob = new Blob([exportEvidencePackToMarkdown(pack, t)], { type: 'text/markdown;charset=utf-8' });
    triggerDownload(blob, `${baseName}.md`);
  } else {
    const blob = new Blob([exportEvidencePackToJson(pack)], { type: 'application/json;charset=utf-8' });
    triggerDownload(blob, `${baseName}.json`);
  }
}
