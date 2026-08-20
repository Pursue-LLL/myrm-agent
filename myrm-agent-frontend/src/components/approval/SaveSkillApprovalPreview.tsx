'use client';

/**
 * [INPUT]
 * - @/lib/approval/saveSkillApproval::normalizeSaveSkillPreviewArgs (POS: args 归一化)
 * - @/components/primitives/collapsible (POS: 折叠 UI)
 *
 * [OUTPUT]
 * - SaveSkillApprovalPreview: save_skill / skill_manage save 审批预览面
 *
 * [POS]
 * 对齐 OpenWorker SaveSkillPreview：description、instructions 折叠预览、bundle 文件 chip、footer。
 */

import { useMemo, useState } from 'react';
import { FileText } from 'lucide-react';

import { basenamePath, normalizeSaveSkillPreviewArgs } from '@/lib/approval/saveSkillApproval';

const PREVIEW_LINES = 5;
const PREVIEW_CHARS = 420;

interface SaveSkillApprovalPreviewProps {
  toolInput: Record<string, unknown>;
  showFullInstructionsLabel: string;
  showLessLabel: string;
  showAllLinesLabel: string;
  footerText: string;
}

function InstructionsPreview({
  text,
  showFullLabel,
  showLessLabel,
  showAllLinesLabel,
}: {
  text: string;
  showFullLabel: string;
  showLessLabel: string;
  showAllLinesLabel: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const lines = text.split('\n');
  const clipped = lines.length > PREVIEW_LINES || text.length > PREVIEW_CHARS;

  const shown = useMemo(() => {
    if (expanded || !clipped) {
      return text;
    }
    let preview = lines.slice(0, PREVIEW_LINES).join('\n');
    if (preview.length > PREVIEW_CHARS) {
      preview = `${preview.slice(0, PREVIEW_CHARS).trimEnd()}…`;
    }
    return preview;
  }, [clipped, expanded, lines, text]);

  return (
    <div className="rounded-md border bg-muted/30 px-3 py-2 text-xs leading-relaxed whitespace-pre-wrap break-words">
      {shown}
      {clipped ? (
        <button
          type="button"
          className="mt-2 block text-xs text-primary hover:underline"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded
            ? showLessLabel
            : lines.length > PREVIEW_LINES
              ? showAllLinesLabel.replace('{count}', String(lines.length))
              : showFullLabel}
        </button>
      ) : null}
    </div>
  );
}

export default function SaveSkillApprovalPreview({
  toolInput,
  showFullInstructionsLabel,
  showLessLabel,
  showAllLinesLabel,
  footerText,
}: SaveSkillApprovalPreviewProps) {
  const preview = useMemo(() => normalizeSaveSkillPreviewArgs(toolInput), [toolInput]);
  const hasFiles = Boolean(preview.files && preview.files.length > 0);

  return (
    <div className="space-y-2.5" data-testid="save-skill-approval-preview">
      {preview.description ? <p className="text-sm text-foreground/90 leading-relaxed">{preview.description}</p> : null}

      {preview.instructions ? (
        <InstructionsPreview
          text={preview.instructions}
          showFullLabel={showFullInstructionsLabel}
          showLessLabel={showLessLabel}
          showAllLinesLabel={showAllLinesLabel}
        />
      ) : null}

      {hasFiles ? (
        <div className="flex flex-wrap gap-1.5" data-testid="skill-bundle-files">
          {preview.files!.map((filePath, index) => (
            <span
              key={`${filePath}-${index}`}
              className="inline-flex items-center gap-1 rounded-md border bg-background px-2 py-1 text-xs text-muted-foreground"
            >
              <FileText className="h-3 w-3 shrink-0" />
              <span className="truncate max-w-[180px]" title={filePath}>
                {basenamePath(filePath)}
              </span>
            </span>
          ))}
        </div>
      ) : null}

      <p className="text-xs text-muted-foreground leading-relaxed">{footerText}</p>
    </div>
  );
}
