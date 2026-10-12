/**
 * Presentation model for the browser diagnostics card.
 *
 * [INPUT]
 * - `GET /api/v1/health/browser/doctor` payload shape (checks carry English message/fix + structured details)
 *
 * [OUTPUT]
 * - BrowserDoctorReport / DoctorCheck: payload types
 * - DOCTOR_HINT_KEYS: every locale key a hint can reference (locale tests iterate it)
 * - buildDoctorView: per-check tone, localized hint descriptor, report-level counts
 * - statusLabelKey: status chip label key of a row
 *
 * [POS]
 * BrowserDoctorCard 的纯逻辑层（无 React）：把后端英文诊断结果归类为用户可读的语气与提示键；
 * 原始 message/fix 仅作为「技术详情」展示，分类只依赖 status 与结构化 details，不解析英文文案。
 */

export interface DoctorCheck {
  status: string;
  message: string;
  fix?: string | null;
  details?: Record<string, unknown> | null;
}

export interface BrowserDoctorReport {
  summary: string;
  overall_healthy: boolean;
  checks: Record<string, DoctorCheck>;
  recommendations: string[];
}

/** optional: a warning that only reports an optional capability that is not set up. */
export type DoctorTone = 'ok' | 'optional' | 'attention' | 'error';

export const DOCTOR_HINT_KEYS = [
  'optionalCamoufox',
  'optionalExtension',
  'memoryOk',
  'memoryLow',
  'diskOk',
  'diskLow',
  'orphansFound',
  'attentionGeneric',
  'errorGeneric',
] as const;

export type DoctorHintKey = (typeof DOCTOR_HINT_KEYS)[number];

export interface DoctorHint {
  key: DoctorHintKey;
  values?: { size: number };
}

export interface DoctorRow {
  name: string;
  check: DoctorCheck;
  tone: DoctorTone;
  hint: DoctorHint | null;
}

export interface DoctorView {
  rows: DoctorRow[];
  /** Rows that need the user's attention (attention + error tones); optional rows never count. */
  needsAttention: number;
  optionalCount: number;
  hasFailure: boolean;
  healthy: boolean;
}

export type StatusLabelKey = 'statusOk' | 'statusOptional' | 'statusWarning' | 'statusError' | 'statusMissing';

const OPTIONAL_HINTS: ReadonlyMap<string, DoctorHintKey> = new Map<string, DoctorHintKey>([
  ['camoufox', 'optionalCamoufox'],
  ['extension_relay', 'optionalExtension'],
]);

const RESOURCE_HINTS = {
  memory: { ok: 'memoryOk', low: 'memoryLow' },
  disk: { ok: 'diskOk', low: 'diskLow' },
} as const;

function classifyTone(check: DoctorCheck): DoctorTone {
  if (check.status === 'ok') {
    return 'ok';
  }
  if (check.status === 'error' || check.status === 'missing') {
    return 'error';
  }
  // Unknown statuses degrade to a visible warning rather than being hidden.
  return check.details?.optional === true ? 'optional' : 'attention';
}

function readFiniteNumber(details: DoctorCheck['details'], key: string): number | null {
  const value = details?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function describeCheck(name: string, check: DoctorCheck, tone: DoctorTone): DoctorHint | null {
  if (tone === 'optional') {
    const key = OPTIONAL_HINTS.get(name);
    return key ? { key } : null;
  }
  if (name === 'memory' || name === 'disk') {
    const availableGb = readFiniteNumber(check.details, 'available_gb');
    if (availableGb !== null) {
      const hints = RESOURCE_HINTS[name];
      return { key: tone === 'ok' ? hints.ok : hints.low, values: { size: Math.round(availableGb * 10) / 10 } };
    }
  }
  if (name === 'orphan_processes' && tone !== 'ok') {
    return { key: 'orphansFound' };
  }
  if (tone === 'attention') {
    return { key: 'attentionGeneric' };
  }
  return tone === 'error' ? { key: 'errorGeneric' } : null;
}

export function buildDoctorView(report: BrowserDoctorReport): DoctorView {
  const rows = Object.entries(report.checks).map(([name, check]): DoctorRow => {
    const tone = classifyTone(check);
    return { name, check, tone, hint: describeCheck(name, check, tone) };
  });
  const countOf = (tone: DoctorTone) => rows.filter((row) => row.tone === tone).length;
  const failures = countOf('error');
  const needsAttention = failures + countOf('attention');
  return {
    rows,
    needsAttention,
    optionalCount: countOf('optional'),
    hasFailure: failures > 0,
    healthy: report.overall_healthy && needsAttention === 0,
  };
}

export function statusLabelKey(tone: DoctorTone, status: string): StatusLabelKey {
  switch (tone) {
    case 'ok':
      return 'statusOk';
    case 'optional':
      return 'statusOptional';
    case 'error':
      return status === 'missing' ? 'statusMissing' : 'statusError';
    case 'attention':
      return 'statusWarning';
  }
}
