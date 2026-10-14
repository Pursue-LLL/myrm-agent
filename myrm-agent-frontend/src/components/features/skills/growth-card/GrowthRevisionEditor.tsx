/**
 * [INPUT] LazyMonacoDiffEditor; next-intl `settings.skills.growth.actions`
 * [OUTPUT] GrowthRevisionEditor: 提案就地修订面板（Monaco DiffEditor + 取消/保存）
 * [POS] features/skills/growth-card 卡片的修订编辑区；内容与提交由父卡片持有
 */
'use client';

import { useTranslations } from 'next-intl';
import { Check, X } from 'lucide-react';
import type { DiffOnMount } from '@monaco-editor/react';
import { LazyMonacoDiffEditor } from '@/components/features/app-shell/lazy-monaco-editor';
import { Button } from '@/components/primitives/button';

interface GrowthRevisionEditorProps {
  originalContent: string;
  editedContent: string;
  isProcessing: boolean;
  isDark: boolean;
  isMobile: boolean;
  onMount: DiffOnMount;
  onCancel: () => void;
  onSave: () => void;
}

export function GrowthRevisionEditor({
  originalContent,
  editedContent,
  isProcessing,
  isDark,
  isMobile,
  onMount,
  onCancel,
  onSave,
}: GrowthRevisionEditorProps) {
  const t = useTranslations('settings.skills.growth');

  return (
    <div className="mt-4 rounded-xl border bg-muted/20 p-3">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('actions.reviseLabel')}</p>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={isProcessing}>
            <X className="mr-1 h-3.5 w-3.5" />
            {t('actions.cancelRevise')}
          </Button>
          <Button size="sm" onClick={onSave} disabled={isProcessing || !editedContent.trim()}>
            <Check className="mr-1 h-3.5 w-3.5" />
            {t('actions.saveRevision')}
          </Button>
        </div>
      </div>
      <div className="rounded-xl border overflow-hidden bg-background h-[300px] md:h-[400px]">
        <LazyMonacoDiffEditor
          height="100%"
          original={originalContent}
          modified={editedContent}
          theme={isDark ? 'vs-dark' : 'light'}
          onMount={onMount}
          options={{
            readOnly: false,
            renderSideBySide: !isMobile,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            wordWrap: 'on',
            lineNumbersMinChars: 3,
            padding: { top: 12, bottom: 12 },
            originalEditable: false,
          }}
        />
      </div>
    </div>
  );
}
