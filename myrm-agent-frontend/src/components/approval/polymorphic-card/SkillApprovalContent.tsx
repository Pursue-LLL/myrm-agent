'use client';

import { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import {
  LazyMonacoEditor as Editor,
  LazyMonacoDiffEditor as DiffEditor,
} from '@/components/features/app-shell/lazy-monaco-editor';

/** A drafted or patched skill with the reason it was proposed; its content opens as a diff when there is an original. */
export function SkillApprovalContent({
  reason,
  content,
  originalContent,
  language,
  label,
  viewChangesLabel,
  hideChangesLabel,
}: {
  reason?: string;
  content?: string;
  originalContent?: string;
  language: string;
  label: string;
  viewChangesLabel: string;
  hideChangesLabel: string;
}) {
  const [showDiff, setShowDiff] = useState(false);

  return (
    <div className="space-y-3">
      <h4 className="font-medium text-sm text-muted-foreground">{label}</h4>
      {reason && <p className="text-sm text-foreground">{reason}</p>}
      <button
        type="button"
        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
        onClick={() => setShowDiff(!showDiff)}
      >
        {showDiff ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        {showDiff ? hideChangesLabel : viewChangesLabel}
      </button>
      {showDiff && (
        <div className="rounded-lg border overflow-hidden h-[400px]">
          {originalContent ? (
            <DiffEditor
              height="400px"
              language={language}
              original={String(originalContent)}
              modified={String(content || '')}
              options={{
                readOnly: true,
                minimap: { enabled: false },
                wordWrap: 'on',
              }}
            />
          ) : (
            <Editor
              height="400px"
              language={language}
              value={String(content || '')}
              options={{
                readOnly: true,
                minimap: { enabled: false },
                wordWrap: 'on',
              }}
            />
          )}
        </div>
      )}
    </div>
  );
}
