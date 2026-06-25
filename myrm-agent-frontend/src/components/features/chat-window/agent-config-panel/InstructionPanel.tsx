'use client';

import { Loader2, Eye } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Switch } from '@/components/primitives/switch';
import dynamic from 'next/dynamic';

const SmartPromptEditor = dynamic(() => import('./SmartPromptEditor').then((mod) => mod.SmartPromptEditor), {
  ssr: false,
  loading: () => (
    <div className="w-full h-[300px] flex items-center justify-center bg-secondary border rounded-lg text-sm text-muted-foreground">
      <Loader2 size={18} className="animate-spin" />
    </div>
  ),
});

export interface InstructionPanelProps {
  localPrompt: string;
  setLocalPrompt: (value: string) => void;
  localUseGlobalInstruction: boolean;
  setLocalUseGlobalInstruction: (value: boolean) => void;
  isSystemPromptHidden: boolean;
  loadingSystemPrompt: boolean;
  onShowSystemPrompt?: () => void;
  onAiGenerate: (intent: string) => Promise<void>;
  isGeneratingAi: boolean;
  history: Array<{ id: string; version: number; systemPrompt: string; createdAt: string }>;
  t: (key: string) => string;
  tCommon: (key: string) => string;
}

export const InstructionPanel = ({
  localPrompt,
  setLocalPrompt,
  localUseGlobalInstruction,
  setLocalUseGlobalInstruction,
  isSystemPromptHidden,
  loadingSystemPrompt,
  onShowSystemPrompt,
  onAiGenerate,
  isGeneratingAi,
  history,
  t,
  tCommon,
}: InstructionPanelProps) => {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50 border border-border/50">
        <div className="flex-1 pr-4">
          <h4 className="text-sm font-medium text-foreground">{t('useGlobalInstruction')}</h4>
          <p className="text-xs text-muted-foreground mt-0.5">{t('useGlobalInstructionDesc')}</p>
        </div>
        <Switch checked={localUseGlobalInstruction} onCheckedChange={setLocalUseGlobalInstruction} />
      </div>

      {isSystemPromptHidden && localPrompt === '⚠️ [Hidden for security]' && (
        <div className="p-4 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800">
          <div className="flex items-center justify-between">
            <div className="flex-1">
              <h4 className="text-sm font-medium text-amber-900 dark:text-amber-100">{t('systemPromptHidden')}</h4>
              <p className="text-xs text-amber-700 dark:text-amber-300 mt-1">{t('systemPromptHiddenDesc')}</p>
            </div>
            <Button onClick={onShowSystemPrompt} disabled={loadingSystemPrompt} variant="outline" size="sm" className="ml-4 gap-2">
              {loadingSystemPrompt ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  {tCommon('loading')}
                </>
              ) : (
                <>
                  <Eye size={14} />
                  {t('showPrompt')}
                </>
              )}
            </Button>
          </div>
        </div>
      )}

      <SmartPromptEditor
        value={localPrompt}
        onChange={setLocalPrompt}
        onAiGenerate={onAiGenerate}
        isGenerating={isGeneratingAi}
        history={history}
        onRestoreHistory={(h) => setLocalPrompt(h.systemPrompt || '')}
        className="w-full h-[300px]"
      />
    </div>
  );
};
