'use client';

/**
 * [INPUT]
 * @/store/chat/types::StagedArtifactView
 *
 * [OUTPUT]
 * StagedArtifactsNotice: Notification banner for automatically staged unwritten deliverables.
 *
 * [POS]
 * Renders in MessageBox when the assistant generated code/documents but omitted persisting them,
 * providing immediate transparency that the files were safely preserved in the sandbox.
 */

import React, { useState } from 'react';
import { FileCode2, ChevronDown, ChevronRight, FolderCheck } from 'lucide-react';
import type { StagedArtifactView } from '@/store/chat/types';

interface StagedArtifactsNoticeProps {
  stagedArtifacts: StagedArtifactView[];
}

export function StagedArtifactsNotice({ stagedArtifacts }: StagedArtifactsNoticeProps) {
  const [expanded, setExpanded] = useState(false);

  if (!stagedArtifacts || stagedArtifacts.length === 0) {
    return null;
  }

  const count = stagedArtifacts.length;

  return (
    <div
      data-testid="staged-artifacts-notice"
      className="mt-2.5 border border-primary/20 dark:border-primary/30 rounded-lg overflow-hidden bg-primary/5 dark:bg-primary/10 transition-colors"
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center justify-between w-full px-3 py-2 text-xs font-medium text-left hover:bg-primary/10 dark:hover:bg-primary/15 transition-colors text-foreground"
      >
        <div className="flex items-center gap-2">
          <FolderCheck className="w-4 h-4 text-primary shrink-0" />
          <span>
            已自动暂存 {count} 个未落盘工件草案至工作区
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <span className="text-[11px] font-mono">.myrm/staged_artifacts/</span>
          {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        </div>
      </button>

      {expanded && (
        <div className="px-3 pb-2.5 pt-1 space-y-1.5 border-t border-primary/10 text-xs text-muted-foreground">
          {stagedArtifacts.map((artifact) => (
            <div
              key={artifact.artifact_id}
              className="flex items-center justify-between py-1 px-2 rounded bg-background/50 border border-border/40 font-mono text-[11px]"
            >
              <div className="flex items-center gap-2 truncate">
                <FileCode2 className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                <span className="text-foreground font-medium truncate">{artifact.filename}</span>
                {artifact.original_hint && (
                  <span className="text-muted-foreground/70 text-[10px]">({artifact.original_hint})</span>
                )}
              </div>
              <div className="flex items-center gap-3 shrink-0 text-[10px] text-muted-foreground">
                <span>{artifact.line_count} 行</span>
                <span>{(artifact.size_bytes / 1024).toFixed(1)} KB</span>
              </div>
            </div>
          ))}
          <div className="text-[10px] text-muted-foreground/80 pt-1">
            这些文件已保全在沙箱环境，您可随时在左侧文件树中查看或重命名采纳。
          </div>
        </div>
      )}
    </div>
  );
}
