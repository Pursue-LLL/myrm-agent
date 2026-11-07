'use client';

import { useTranslations } from 'next-intl';
import { LazyMonacoEditor as Editor } from '@/components/features/app-shell/lazy-monaco-editor';
import type { ApprovalPayload } from '@/store/useApprovalStore';

interface ToolClarificationContentProps {
  approval: ApprovalPayload;
  editedArgs: string;
  onEditedArgsChange: (value: string) => void;
}

/** The failed tool call's error and an editor for the arguments the user fixes before approving a retry. */
export function ToolClarificationContent({ approval, editedArgs, onEditedArgsChange }: ToolClarificationContentProps) {
  const t = useTranslations('toolApproval');
  const errorMsg = approval.reason || t('toolExecutionFailed');

  return (
    <div className="space-y-4">
      <h4 className="font-medium text-sm text-red-500">{t('clarificationRequired')}</h4>
      <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive-text whitespace-pre-wrap">
        {errorMsg}
      </div>

      <div className="space-y-2">
        <label className="text-sm font-medium text-muted-foreground">{t('fixParameters')}</label>
        <div className="rounded-lg border overflow-hidden h-[200px]">
          <Editor
            height="200px"
            language="json"
            value={editedArgs}
            onChange={(val) => onEditedArgsChange(val || '')}
            options={{
              minimap: { enabled: false },
              wordWrap: 'on',
            }}
          />
        </div>
      </div>
    </div>
  );
}
