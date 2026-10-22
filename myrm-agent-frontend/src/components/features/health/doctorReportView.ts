/**
 * Presentation model for the system doctor rows.
 *
 * [INPUT]
 * - services/runtime-health.ts::HealthReport (POS: probe payload; message / fix / detail are English by contract)
 *
 * [OUTPUT]
 * - DOCTOR_LOCALE_KEYS: every locale key a row can reference (locale tests iterate it)
 * - describeReport: localized title / summary descriptors plus the technical lines of one report
 * - DoctorText / TechnicalLine / ReportView: descriptor types
 *
 * [POS]
 * DoctorDashboard 的纯逻辑层（无 React）：把后端英文体检结果映射为本地化文案键；
 * 原始 message / fix / detail / measured / expected / cause 只作为「技术详情」呈现，分类只依赖 status 与 component_name，
 * 不解析英文文案。
 */

import type { HealthReport, HealthStatus } from '@/services/runtime-health';

type AttentionStatus = Exclude<HealthStatus, 'pass'>;

export type DoctorText = { key: string; values?: Record<string, unknown> } | { text: string };

export interface TechnicalLine {
  labelKey: string;
  value: string;
}

export interface ReportView {
  title: DoctorText;
  summary: DoctorText;
  technical: TechnicalLine[];
}

/** Components that carry a localized title; the manager names a timed-out hook after its Python function instead. */
const COMPONENT_NAMES = [
  'AgentColdStart',
  'AgentEngine',
  'AgentPromptCacheAlignment',
  'AgentStepBudget',
  'Database',
  'DesktopControl',
  'DesktopLockedUse',
  'DLQ',
  'ExecutionCache',
  'GatewayRuntime',
  'HookSystem',
  'Network',
  'OllamaContext',
  'OrphanSession',
  'SkillEcosystem',
  'SupplyChainSecurity',
  'SystemExhaustion',
  'SystemResources',
  'Tokenizer',
  'TraceExportAudit',
  'TraceExportSecurity',
  'VectorDB',
  'WorkspaceStorage',
] as const;

/** Statuses whose verdict has a hint written for that component; every other combination uses the generic hint. */
const COMPONENT_HINT_STATUSES: Readonly<Record<string, readonly AttentionStatus[]>> = {
  AgentEngine: ['fail'],
  Database: ['fail'],
  DLQ: ['warn'],
  GatewayRuntime: ['warn', 'fail'],
  Network: ['fail'],
  SupplyChainSecurity: ['warn', 'fail'],
  SystemExhaustion: ['warn', 'fail'],
  SystemResources: ['warn', 'fail'],
  Tokenizer: ['warn', 'fail'],
  VectorDB: ['warn', 'fail'],
  WorkspaceStorage: ['warn', 'fail'],
};

const TECHNICAL_FIELDS = [
  ['message', 'technical.message'],
  ['detail', 'technical.detail'],
  ['measured', 'technical.measured'],
  ['expected', 'technical.expected'],
  ['cause', 'technical.cause'],
  ['fix_suggestion', 'technical.fix'],
] as const satisfies readonly (readonly [keyof HealthReport, string])[];

export const DOCTOR_LOCALE_KEYS: readonly string[] = [
  'status.pass',
  'status.warn',
  'status.fail',
  'technical.toggle',
  'technical.component',
  ...TECHNICAL_FIELDS.map(([, key]) => key),
  'components.generic',
  ...COMPONENT_NAMES.map((name) => `components.${name}`),
  'hints.generic.warn',
  'hints.generic.fail',
  ...Object.entries(COMPONENT_HINT_STATUSES).flatMap(([name, statuses]) =>
    statuses.map((status) => `hints.${name}.${status}`),
  ),
];

const KNOWN_COMPONENTS: ReadonlySet<string> = new Set(COMPONENT_NAMES);

// A hook that timed out or crashed is reported under its function name, e.g. `check_network_health`.
const INTERNAL_HOOK_NAME = /^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$/;

function describeTitle(componentName: string, hasKey: (key: string) => boolean): DoctorText {
  if (KNOWN_COMPONENTS.has(componentName) && hasKey(`components.${componentName}`)) {
    return { key: `components.${componentName}` };
  }
  return INTERNAL_HOOK_NAME.test(componentName) ? { key: 'components.generic' } : { text: componentName };
}

function describeSummary(report: HealthReport, hasKey: (key: string) => boolean): DoctorText {
  // A verdict code with a locale entry wins; an unmapped code falls through instead of leaking the key path.
  if (report.code) {
    const key = `errors.${report.code}.message`;
    if (hasKey(key)) {
      return { key, values: report.meta_data ?? undefined };
    }
  }
  if (report.status === 'pass') {
    return { text: report.message };
  }
  const dedicatedKey = `hints.${report.component_name}.${report.status}`;
  const hasDedicatedHint = COMPONENT_HINT_STATUSES[report.component_name]?.includes(report.status) ?? false;
  if (hasDedicatedHint && hasKey(dedicatedKey)) {
    return { key: dedicatedKey };
  }
  return { key: `hints.generic.${report.status}` };
}

export function describeReport(report: HealthReport, hasKey: (key: string) => boolean): ReportView {
  const title = describeTitle(report.component_name, hasKey);
  const summary = describeSummary(report, hasKey);
  const technical: TechnicalLine[] = [];
  // The raw component name only helps support when the row shows a friendlier title instead.
  if ('key' in title) {
    technical.push({ labelKey: 'technical.component', value: report.component_name });
  }
  for (const [field, labelKey] of TECHNICAL_FIELDS) {
    const value = report[field];
    // The English message is redundant while it is itself the visible summary.
    if (typeof value === 'string' && value !== '' && !(field === 'message' && 'text' in summary)) {
      technical.push({ labelKey, value });
    }
  }
  return { title, summary, technical };
}
