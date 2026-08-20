/**
 * [INPUT]
 * - Button (POS: 统一交互按钮)
 *
 * [OUTPUT]
 * - FlowPadInlineResultPanel: Inline 结果展示 + Paste/Copy 操作区。
 *
 * [POS]
 * FlowPad Inline 模式结果区子组件。隔离结果渲染与回写操作，减少主组件复杂度。
 */
import { ClipboardPaste, Copy, Loader2 } from 'lucide-react';

import { Button } from '@/components/primitives/button';

interface FlowPadInlineResultPanelProps {
  mode: 'chat' | 'inline';
  inlineResult: string;
  inlineGenerating: boolean;
  onPasteBack: () => void;
  onCopyResult: () => void;
  t: (key: string) => string;
}

export function FlowPadInlineResultPanel({
  mode,
  inlineResult,
  inlineGenerating,
  onPasteBack,
  onCopyResult,
  t,
}: FlowPadInlineResultPanelProps) {
  if (mode !== 'inline' || !inlineResult) {
    return null;
  }

  return (
    <>
      <div className="px-4 py-3 border-b border-border/30 bg-muted/5 max-h-[200px] overflow-y-auto">
        <p className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">{inlineResult}</p>
        {inlineGenerating && (
          <span className="inline-flex items-center gap-1 mt-1 text-xs text-muted-foreground">
            <Loader2 className="w-3 h-3 animate-spin" />
            {t('generating')}
          </span>
        )}
      </div>

      {!inlineGenerating && (
        <div className="px-4 py-2.5 border-b border-border/20 flex items-center gap-2">
          <Button size="sm" className="h-7 gap-1.5 text-xs" onClick={onPasteBack}>
            <ClipboardPaste className="w-3 h-3" />
            {t('pasteBack')}
          </Button>
          <Button size="sm" variant="outline" className="h-7 gap-1.5 text-xs" onClick={onCopyResult}>
            <Copy className="w-3 h-3" />
            {t('copyResult')}
          </Button>
        </div>
      )}
    </>
  );
}
