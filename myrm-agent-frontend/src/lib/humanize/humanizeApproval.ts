import { extractContextFromToolInput } from './extractContext';
import { humanizeToolLine } from './humanizeToolLine';
import type { TranslateFn } from './types';

export function humanizeApprovalTitle(toolName: string, toolInput: Record<string, unknown>, t: TranslateFn): string {
  const ctx = extractContextFromToolInput(toolInput);
  return humanizeToolLine(toolName, ctx, t, 'approval');
}
