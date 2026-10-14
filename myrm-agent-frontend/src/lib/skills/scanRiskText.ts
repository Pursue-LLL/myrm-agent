/**
 * [INPUT] none (pure functions over a next-intl translator scoped to `settings.skills.scanRisk`)
 * [OUTPUT] parseRiskSignals / threatTypeLabel / severityLabel / riskSignalLabel / riskRemediation:
 *          技能安全扫描结论与待审原因的本地化文案（threat 类别、严重度、待审信号、处置建议）
 * [POS] 技能成长卡片、本地技能预览、技能详情共用的扫描文案出口；服务端只下发稳定的类别码与信号码，
 *       这里把它们翻译成用户语言，类别码以封闭词表判定（译文键也以此为准，由 i18n 同步测试守住与扫描器一致），
 *       词表之外的类别显示「其他风险」，不向用户暴露内部代码。
 */

export type ScanRiskTranslate = (key: string, values?: Record<string, string | number>) => string;

/** Threat classes the skill scanner can report (harness `scanning/patterns.py` groups plus the Unicode, AST, audit and package passes). */
export const SCAN_THREAT_TYPES: readonly string[] = [
  'prompt_injection',
  'command_injection',
  'credential_exposure',
  'data_exfiltration',
  'filesystem_access',
  'process_operation',
  'network_access',
  'screen_input',
  'memory_config_snooping',
  'code_injection',
  'privilege_escalation',
  'environment_manipulation',
  'reflection',
  'deserialization',
  'log_audit_tampering',
  'scheduled_task_injection',
  'container_escape',
  'memory_manipulation',
  'dns_tunneling',
  'supply_chain',
  'obfuscation',
  'destructive',
  'persistence',
  'path_traversal',
  'crypto_mining',
  'reverse_shell',
  'prompt_secret_exfiltration',
  'invisible_unicode',
  'dangerous_import',
  'ast_parse_error',
  'llm_audit',
  'invalid_manifest',
  'integrity',
  'missing_artifact',
  'empty_artifact',
];

export const SCAN_SEVERITIES: readonly string[] = ['critical', 'high', 'medium', 'low', 'info'];

const RISK_REASON_PREFIX = 'risk:';
const NEW_FINDING_PREFIX = 'new_high_finding:';
const DIFF_RANGE_PREFIX = 'diff_range:';
const SCAN_UNAVAILABLE = 'scan_unavailable';
/** e.g. `low_effective_rate:20%(5runs)` */
const LOW_EFFECTIVE_RATE = /^low_effective_rate:(\d+%)\((\d+)runs\)$/;

type ClassifiedSignal =
  | { kind: 'newHighFinding'; threatType: string }
  | { kind: 'scanUnavailable' }
  | { kind: 'diffRange'; percent: string }
  | { kind: 'lowEffectiveRate'; rate: string; runs: string }
  | { kind: 'unknown' };

function classifySignal(signal: string): ClassifiedSignal {
  if (signal === SCAN_UNAVAILABLE) {
    return { kind: 'scanUnavailable' };
  }
  if (signal.startsWith(NEW_FINDING_PREFIX)) {
    return { kind: 'newHighFinding', threatType: signal.slice(NEW_FINDING_PREFIX.length) };
  }
  if (signal.startsWith(DIFF_RANGE_PREFIX)) {
    const percent = signal.slice(DIFF_RANGE_PREFIX.length);
    return percent ? { kind: 'diffRange', percent } : { kind: 'unknown' };
  }
  const lowRate = LOW_EFFECTIVE_RATE.exec(signal);
  if (lowRate) {
    return { kind: 'lowEffectiveRate', rate: lowRate[1], runs: lowRate[2] };
  }
  return { kind: 'unknown' };
}

/** Signals behind a `risk:a,b` reason code; empty for any other reason code. */
export function parseRiskSignals(reasonCode: string | null | undefined): string[] {
  if (!reasonCode?.startsWith(RISK_REASON_PREFIX)) {
    return [];
  }
  return reasonCode
    .slice(RISK_REASON_PREFIX.length)
    .split(',')
    .filter((signal) => signal.length > 0);
}

export function threatTypeLabel(t: ScanRiskTranslate, threatType: string): string {
  return SCAN_THREAT_TYPES.includes(threatType) ? t(`threat.${threatType}`) : t('threat.unknown');
}

/** Severities outside the closed vocabulary are shown as sent. */
export function severityLabel(t: ScanRiskTranslate, severity: string): string {
  return SCAN_SEVERITIES.includes(severity) ? t(`severity.${severity}`) : severity;
}

export function riskSignalLabel(t: ScanRiskTranslate, signal: string): string {
  const classified = classifySignal(signal);
  switch (classified.kind) {
    case 'newHighFinding':
      return t('signal.newHighFinding', { threat: threatTypeLabel(t, classified.threatType) });
    case 'scanUnavailable':
      return t('signal.scanUnavailable');
    case 'diffRange':
      return t('signal.diffRange', { percent: classified.percent });
    case 'lowEffectiveRate':
      return t('signal.lowEffectiveRate', { rate: classified.rate, runs: classified.runs });
    case 'unknown':
      return t('signal.unknown');
  }
}

/** One sentence per distinct kind of signal, in the order the signals arrived; unknown signals add none. */
export function riskRemediation(t: ScanRiskTranslate, signals: readonly string[]): string[] {
  const kinds = new Set<string>();
  for (const signal of signals) {
    const classified = classifySignal(signal);
    if (classified.kind !== 'unknown') {
      kinds.add(classified.kind);
    }
  }
  return Array.from(kinds, (kind) => t(`remediation.${kind}`));
}
