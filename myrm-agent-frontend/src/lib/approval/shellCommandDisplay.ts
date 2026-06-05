/** Shell tool names that carry executable command text in approval payloads. */
const SHELL_APPROVAL_TOOL_NAMES = new Set([
  'bash_code_execute_tool',
  'bash_tool',
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

export interface IndexedCommandSpan {
  span: CommandSpan;
  risk: SpanRiskLevel | undefined;
}

/** Zip spans with parallel risks, then sort by startIndex for stable rendering. */
export function zipSpansWithRisks(
  spans: CommandSpan[],
  risks: SpanRiskLevel[] | undefined,
): IndexedCommandSpan[] {
  const indexed = spans.map((span, index) => ({ span, risk: risks?.[index] }));
  return [...indexed].sort((a, b) => a.span.startIndex - b.span.startIndex);
}
