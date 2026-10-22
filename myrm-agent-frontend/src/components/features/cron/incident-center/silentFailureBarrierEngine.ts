/**
 * Silent Failure Verification Barrier & Incident Classification Engine
 * 假成功静默失败熔断门禁与事故分类计算引擎
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any；
 * 2. 所有 if 显式包裹大括号；
 * 3. 行数严格受控在 400 行以内。
 */

import {
  AcceptanceVerificationResult,
  ArtifactAcceptanceCriteria,
  CronIncident,
  IncidentCategory,
  IncidentMetrics,
  IncidentSeverity,
  TaskExecutionRun,
} from './cronIncidentTypes';

export function verifyArtifactAcceptance(
  run: TaskExecutionRun,
  criteria?: ArtifactAcceptanceCriteria
): AcceptanceVerificationResult {
  const effectiveCriteria: ArtifactAcceptanceCriteria = criteria || {
    minOutputBytes: 1,
    requiredArtifacts: [],
    contentKeywords: [],
    allowZeroByteIfNoError: false,
  };

  const totalBytes = run.generatedArtifacts.reduce((sum, item) => sum + item.bytes, 0);
  const reasons: string[] = [];
  const missingArtifacts: string[] = [];
  const missingKeywords: string[] = [];

  // 1. 物理检查目标文件是否存在
  if (effectiveCriteria.requiredArtifacts && effectiveCriteria.requiredArtifacts.length > 0) {
    const artifactNames = new Set(run.generatedArtifacts.map((a) => a.name));
    for (const requiredName of effectiveCriteria.requiredArtifacts) {
      if (!artifactNames.has(requiredName)) {
        missingArtifacts.push(requiredName);
        reasons.push(`缺失预期交付物文件: ${requiredName}`);
      }
    }
  }

  // 2. 检查产物体积，彻底杜绝 0 字节摸鱼
  const minBytes = effectiveCriteria.minOutputBytes ?? 1;
  if (!effectiveCriteria.allowZeroByteIfNoError && totalBytes < minBytes && run.stdout.trim().length === 0) {
    reasons.push(`产物总字节数 (${totalBytes} B) 低于验收基准 (${minBytes} B) 且 stdout 为空`);
  }

  // 3. 检查正文关键结论
  if (effectiveCriteria.contentKeywords && effectiveCriteria.contentKeywords.length > 0) {
    const combinedOutput = `${run.stdout}\n${run.stderr}`;
    for (const keyword of effectiveCriteria.contentKeywords) {
      if (!combinedOutput.includes(keyword)) {
        missingKeywords.push(keyword);
        reasons.push(`执行输出未包含实质性关键结论: "${keyword}"`);
      }
    }
  }

  const passed = reasons.length === 0;
  const isSilentFailure = !passed && run.exitCode === 0;

  return {
    passed,
    isSilentFailure,
    reasons,
    missingArtifacts,
    missingKeywords,
    actualBytes: totalBytes,
  };
}

export function classifyExecutionRun(
  run: TaskExecutionRun,
  criteria?: ArtifactAcceptanceCriteria
): { incident?: CronIncident; passed: boolean } {
  const verification = verifyArtifactAcceptance(run, criteria);

  // 1. 进程正常退出 0，但物理产物验收未通过 -> 假成功静默失败熔断！
  if (run.exitCode === 0 && !verification.passed) {
    const incident: CronIncident = {
      id: `incident-silent-${run.runId}-${Date.now().toString(36)}`,
      jobId: run.jobId,
      jobName: run.jobName,
      runId: run.runId,
      category: 'silent_failure',
      severity: 'critical',
      occurredAt: run.executedAt,
      exitCode: 0,
      summary: `进程返回 exit 0 假成功，但未产出实质交付物`,
      failureReason: verification.reasons.join('; '),
      verificationDetails: verification,
      acknowledged: false,
      retryCount: 0,
    };
    return { passed: false, incident };
  }

  // 2. 进程正常退出 0 且验收通过 -> 真正成功
  if (run.exitCode === 0 && verification.passed) {
    return { passed: true };
  }

  // 3. 进程异常退出 (exit !== 0) -> 深入诊断分类
  const outputText = `${run.stdout} ${run.stderr}`.toLowerCase();
  let category: IncidentCategory = 'runtime_crash';
  let severity: IncidentSeverity = 'critical';
  let summary = `进程非零异常退出 (exit code: ${run.exitCode})`;

  if (outputText.includes('429') || outputText.includes('quota') || outputText.includes('rate limit')) {
    category = 'quota_exhausted';
    severity = 'warning';
    summary = '模型或上游 API 配额超限 (429 Rate Limit)';
  } else if (
    outputText.includes('401') ||
    outputText.includes('unauthorized') ||
    outputText.includes('token expired')
  ) {
    category = 'auth_expired';
    severity = 'critical';
    summary = '调用凭证失效或鉴权失败 (401 Unauthorized)';
  } else if (outputText.includes('timeout') || outputText.includes('timed out') || run.durationMs > 300000) {
    category = 'timeout';
    severity = 'warning';
    summary = '任务执行超时中断 (Execution Timeout)';
  }

  const incident: CronIncident = {
    id: `incident-fail-${run.runId}-${Date.now().toString(36)}`,
    jobId: run.jobId,
    jobName: run.jobName,
    runId: run.runId,
    category,
    severity,
    occurredAt: run.executedAt,
    exitCode: run.exitCode,
    summary,
    failureReason: run.stderr.trim() || run.stdout.trim() || `进程异常退出，状态码 ${run.exitCode}`,
    verificationDetails: verification,
    acknowledged: false,
    retryCount: 0,
  };

  return { passed: false, incident };
}

export function computeIncidentMetrics(incidents: CronIncident[]): IncidentMetrics {
  const unacknowledged = incidents.filter((item) => !item.acknowledged);
  const silentFailures = unacknowledged.filter((item) => item.category === 'silent_failure');
  const criticals = unacknowledged.filter((item) => item.severity === 'critical');

  return {
    totalCount: incidents.length,
    unacknowledgedCount: unacknowledged.length,
    silentFailureCount: silentFailures.length,
    criticalCount: criticals.length,
    hasBlockingIncidents: silentFailures.length > 0 || criticals.length > 0,
  };
}
