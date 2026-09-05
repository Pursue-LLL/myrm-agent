'use client';

import React, { memo } from 'react';
import { useTranslations } from 'next-intl';
import { Check, Sparkles } from 'lucide-react';
import { VERIFIED_TOOL_MODELS, type VerifiedToolModel } from './verifiedToolModels';

interface ToolCallingModelChecklistProps {
  selectedModel?: string;
  onSelectModel: (model: VerifiedToolModel) => void;
  className?: string;
}

export const ToolCallingModelChecklist = memo<ToolCallingModelChecklistProps>(({
  selectedModel,
  onSelectModel,
  className = '',
}) => {
  const t = useTranslations('chat.localCapabilities');

  return (
    <div className={`space-y-3 ${className}`} data-testid=\"tool-calling-checklist\">
      <div className=\"flex items-center justify-between\">
        <div className=\"flex items-center gap-1.5 text-xs font-semibold text-foreground\">
          <Sparkles className=\"h-3.5 w-3.5 text-primary\" />
          <span>{t('checklistTitle')}</span>
        </div>
        <span className=\"text-[11px] text-muted-foreground\">
          {t('checklistSubtitle')}
        </span>
      </div>

      <div className=\"grid grid-cols-1 sm:grid-cols-2 gap-2\">
        {VERIFIED_TOOL_MODELS.map((item) => {
          const isSelected = selectedModel?.toLowerCase().includes(item.id.toLowerCase());

          return (
            <button
              key={item.id}
              type=\"button\"
              onClick={() => onSelectModel(item)}
              data-testid={`btn-select-model-${item.id}`}
              className={`flex items-start justify-between rounded-lg border p-2.5 text-left transition-all ${
                isSelected
                  ? 'border-primary bg-primary/5 ring-1 ring-primary/20'
                  : 'border-border bg-card/60 hover:bg-accent/40'
              }`}
            >
              <div className=\"space-y-0.5 min-w-0 pr-2\">
                <div className=\"flex items-center gap-1.5\">
                  <span className=\"text-xs font-medium text-foreground truncate\">
                    {item.name}
                  </span>
                  {item.recommended && (
                    <span className=\"rounded bg-primary/10 px-1 py-0.2 text-[10px] font-medium text-primary shrink-0\">
                      {t('recommendedBadge')}
                    </span>
                  )}
                </div>
                <div className=\"text-[11px] text-muted-foreground truncate\">
                  {item.provider}
                </div>
              </div>

              <div
                className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-colors mt-0.5 ${
                  isSelected
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-muted-foreground/30 bg-transparent'
                }`}
              >
                {isSelected && <Check className=\"h-2.5 w-2.5 stroke-[3]\" />}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
});

ToolCallingModelChecklist.displayName = 'ToolCallingModelChecklist';
