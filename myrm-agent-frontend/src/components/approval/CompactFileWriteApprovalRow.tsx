'use client';

/**
 * [INPUT]
 * - @/components/features/app-shell/lazy-monaco-editor::Editor (POS: 懒加载 Monaco)
 * - @/components/primitives/collapsible (POS: 折叠 UI 原语)
 *
 * [OUTPUT]
 * - CompactFileWriteApprovalRow: Subagent Drawer 本地文件写 compact 审批行
 *
 * [POS]
 * Approval Drawer 内低风险文件写操作的紧凑展示；Monaco 默认折叠以减 scroll。
 */

import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

import { LazyMonacoEditor as Editor } from '@/components/features/app-shell/lazy-monaco-editor';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/primitives/collapsible';

interface CompactFileWriteApprovalRowProps {
  title: string;
  filePath: string;
  content: string;
  language: string;
  isDark: boolean;
  viewChangesLabel: string;
  hideChangesLabel: string;
  scopeNote?: string;
  scopeExternal?: boolean;
}

export default function CompactFileWriteApprovalRow({
  title,
  filePath,
  content,
  language,
  isDark,
  viewChangesLabel,
  hideChangesLabel,
  scopeNote,
  scopeExternal = false,
}: CompactFileWriteApprovalRowProps) {
  const [open, setOpen] = useState(false);
  const hasContent = content.trim().length > 0;

  return (
    <div className="rounded-lg border bg-muted/20 px-3 py-2.5 space-y-2">
      <div className="flex items-start justify-between gap-2 min-w-0">
        <div className="min-w-0">
          <p className="text-sm font-medium truncate">{title}</p>
          {scopeNote ? (
            <p
              className={`text-xs break-words ${scopeExternal ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground'}`}
            >
              {scopeNote}
            </p>
          ) : null}
          {filePath ? (
            <p className="text-xs text-muted-foreground truncate" title={filePath}>
              {filePath}
            </p>
          ) : null}
        </div>
      </div>

      {hasContent ? (
        <Collapsible open={open} onOpenChange={setOpen}>
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              {open ? hideChangesLabel : viewChangesLabel}
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent className="pt-2">
            <div className="rounded-md border overflow-hidden h-[220px]">
              <Editor
                height="100%"
                language={language}
                theme={isDark ? 'vs-dark' : 'light'}
                value={content}
                options={{
                  readOnly: true,
                  minimap: { enabled: false },
                  wordWrap: 'on',
                }}
              />
            </div>
          </CollapsibleContent>
        </Collapsible>
      ) : null}
    </div>
  );
}
