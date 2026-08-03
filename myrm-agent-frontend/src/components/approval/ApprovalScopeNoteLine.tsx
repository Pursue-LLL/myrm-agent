'use client';

/**
 * [INPUT]
 * - @/lib/humanize::resolveScopeNote (POS: scope SSOT)
 *
 * [OUTPUT]
 * - ApprovalScopeNoteLine: 审批卡 scope 单行文案
 *
 * [POS]
 * 三 outlet 审批卡（Single / Polymorphic / ToolCall）共用的 scope 展示行。
 */

import { resolveScopeNote, type TranslateFn } from '@/lib/humanize';
import { cn } from '@/lib/utils/classnameUtils';

interface ApprovalScopeNoteLineProps {
  toolName: string;
  toolInput: Record<string, unknown>;
  tHumanize: TranslateFn;
  className?: string;
}

/** Plain-words scope hint under approval tool titles (SSOT: resolveScopeNote). */
export default function ApprovalScopeNoteLine({
  toolName,
  toolInput,
  tHumanize,
  className,
}: ApprovalScopeNoteLineProps) {
  const note = resolveScopeNote(toolName, toolInput, tHumanize);

  return (
    <span
      className={cn(
        'text-xs break-words',
        note.external ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground',
        className,
      )}
    >
      {note.text}
    </span>
  );
}
