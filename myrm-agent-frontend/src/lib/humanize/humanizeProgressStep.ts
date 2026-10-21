import type { ProgressItem } from '@/store/chat/types/progress';

import { extractContextFromProgressStep } from './extractContext';
import { humanizeToolLine } from './humanizeToolLine';
import type { TranslateFn } from './types';

/** Human-readable one-liner for a progress step title. Cancelled steps use ask tense. */
export function humanizeProgressStep(step: ProgressItem, t: TranslateFn): string | null {
  const toolName = step.tool_name?.trim();
  if (!toolName) {
    return null;
  }
  const ctx = extractContextFromProgressStep(step);
  const mode = step.status === 'cancelled' ? 'ask' : 'progress';
  return humanizeToolLine(toolName, ctx, t, mode);
}
