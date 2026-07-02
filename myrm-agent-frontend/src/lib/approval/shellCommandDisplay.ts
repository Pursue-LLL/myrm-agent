/** Shell tool names that carry executable command text in approval payloads. */
const SHELL_APPROVAL_TOOL_NAMES = new Set([
  'bash_code_execute_tool',
  'execute_code',
  'shell',
  'execute_command',
  'run_script',
]);

export interface CommandSpan {
  startIndex: number;
  endIndex: number;
}

export type SpanRiskLevel = 'safe' | 'unknown';

export type SpanRiskReason =
  | 'safe'
  | 'empty_segment'
  | 'redirect'
  | 'unknown_command'
  | 'unknown_subcommand'
  | 'invalid_flags';

export interface PlainExplanation {
  en: string;
  zh: string;
}

const SHELL_METADATA_KEYS = new Set([
  'command_spans',
  'commandSpans',
  'command_span_risks',
  'commandSpanRisks',
  'command_span_reasons',
  'commandSpanReasons',
  'plain_explanation',
  'plainExplanation',
]);

const SHELL_EDIT_PREFERRED_KEYS = ['command', 'code', 'script', 'cmd'] as const;

export function isShellApprovalTool(toolName: string): boolean {
  return SHELL_APPROVAL_TOOL_NAMES.has(toolName);
}

export function extractShellCommand(args: Record<string, unknown>): string {
  const raw = args.command ?? args.script ?? args.cmd ?? args.code;
  return typeof raw === 'string' ? raw : '';
}

export function parseCommandSpans(value: unknown, commandLength: number): CommandSpan[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  const spans = value.filter((item): item is CommandSpan => {
    if (typeof item !== 'object' || item === null) {
      return false;
    }
    const { startIndex, endIndex } = item as Record<string, unknown>;
    return (
      Number.isSafeInteger(startIndex) &&
      Number.isSafeInteger(endIndex) &&
      (startIndex as number) >= 0 &&
      (endIndex as number) > (startIndex as number) &&
      (endIndex as number) <= commandLength
    );
  });
  return spans.length > 0 ? spans : undefined;
}

export function parseCommandSpanRisks(
  value: unknown,
  spanCount: number,
): SpanRiskLevel[] | undefined {
  if (!Array.isArray(value) || value.length !== spanCount) {
    return undefined;
  }
  const risks = value.filter((item): item is SpanRiskLevel => item === 'safe' || item === 'unknown');
  return risks.length === spanCount ? risks : undefined;
}

const SPAN_RISK_REASONS: ReadonlySet<string> = new Set([
  'safe',
  'empty_segment',
  'redirect',
  'unknown_command',
  'unknown_subcommand',
  'invalid_flags',
]);

export function parseCommandSpanReasons(
  value: unknown,
  spanCount: number,
): SpanRiskReason[] | undefined {
  if (!Array.isArray(value) || value.length !== spanCount) {
    return undefined;
  }
  const reasons = value.filter((item): item is SpanRiskReason =>
    typeof item === 'string' && SPAN_RISK_REASONS.has(item),
  );
  return reasons.length === spanCount ? reasons : undefined;
}

export function parsePlainExplanation(value: unknown): PlainExplanation | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return undefined;
  }
  const obj = value as Record<string, unknown>;
  if (typeof obj.en === 'string' && typeof obj.zh === 'string') {
    return { en: obj.en, zh: obj.zh };
  }
  return undefined;
}

export function isShellApprovalMetadataKey(key: string): boolean {
  return SHELL_METADATA_KEYS.has(key);
}

/** Remove harness span metadata from shell tool args (not sent back on edit). */
export function stripShellApprovalMetadata(
  args: Record<string, unknown>,
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(args).filter(([key]) => !SHELL_METADATA_KEYS.has(key)),
  );
}

/**
 * Merge user-edited fields onto original tool args.
 * Harness replaces tool args wholesale on edit — preserve timeout, run_in_background, etc.
 */
export function mergeShellEditedArgs(
  originalArgs: Record<string, unknown>,
  editedFields: Record<string, unknown>,
): Record<string, unknown> {
  return {
    ...stripShellApprovalMetadata(originalArgs),
    ...editedFields,
  };
}

/** Editable shell tool args (excludes harness span metadata). */
export function getShellEditInputEntries(
  args: Record<string, unknown>,
): Array<[string, unknown]> {
  const preferredSet = new Set<string>(SHELL_EDIT_PREFERRED_KEYS);
  const preferred = SHELL_EDIT_PREFERRED_KEYS.filter((key) => key in args).map(
    (key) => [key, args[key]] as [string, unknown],
  );
  const rest = Object.entries(args).filter(
    ([key]) => !SHELL_METADATA_KEYS.has(key) && !preferredSet.has(key),
  );
  return [...preferred, ...rest].slice(0, 8);
}

export interface IndexedCommandSpan {
  span: CommandSpan;
  risk: SpanRiskLevel | undefined;
  reason: SpanRiskReason | undefined;
}

/** Zip spans with parallel risks/reasons, then sort by startIndex for stable rendering. */
export function zipSpansWithRisks(
  spans: CommandSpan[],
  risks: SpanRiskLevel[] | undefined,
  reasons?: SpanRiskReason[] | undefined,
): IndexedCommandSpan[] {
  const indexed = spans.map((span, index) => ({
    span,
    risk: risks?.[index],
    reason: reasons?.[index],
  }));
  return [...indexed].sort((a, b) => a.span.startIndex - b.span.startIndex);
}
