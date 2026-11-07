'use client';

/**
 * [INPUT] ./AgentCapabilitiesTab::CapabilitiesSectionProps (POS: 能力 Tab 区段共用 props), @/components/features/app-shell/model-picker-popover (POS: 路由模型选择)
 * [OUTPUT] RoutingOverrideSection: 模型路由覆盖区段（跟随全局 / 自定义 / 关闭，自定义时分别指定轻量与推理模型）
 * [POS] 能力 Tab 的路由覆盖区段，读写 editor.modelSelection 的 routing 字段。
 */

import { cn } from '@/lib/utils/classnameUtils';
import ProviderIcon from '@/components/features/settings/model-service/ProviderIcon';
import ModelPickerPopover from '@/components/features/app-shell/model-picker-popover';
import { X } from 'lucide-react';
import { IconChevronDown } from '@/components/features/icons/PremiumIcons';
import type { AgentCapabilitiesTabProps, CapabilitiesSectionProps } from './AgentCapabilitiesTab';

type RoutingMode = 'global' | 'custom' | 'disabled';

function getRoutingMode(ms: AgentCapabilitiesTabProps['editor']['modelSelection']): RoutingMode {
  if (!ms || ms.routingEnabled === undefined) {
    return 'global';
  }
  return ms.routingEnabled ? 'custom' : 'disabled';
}

export function RoutingOverrideSection({ editor, t }: CapabilitiesSectionProps) {
  const ms = editor.modelSelection;
  const mode = getRoutingMode(ms);

  const setMode = (next: RoutingMode) => {
    if (!ms) {
      return;
    }
    if (next === 'global') {
      const {
        routingEnabled: _,
        lightProviderId: _lp,
        lightModel: _lm,
        reasoningProviderId: _rp,
        reasoningModel: _rm,
        ...rest
      } = ms;
      editor.setModelSelection(rest);
    } else {
      editor.setModelSelection({ ...ms, routingEnabled: next === 'custom' });
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3">
        <h3 className="text-sm font-medium text-foreground">{t('agent.routingOverride')}</h3>
        <p className="text-xs text-muted-foreground mt-0.5">{t('agent.routingOverrideDesc')}</p>
      </div>

      <div className="flex flex-col sm:flex-row gap-2 mb-4">
        {(['global', 'custom', 'disabled'] as const).map((opt) => (
          <button
            key={opt}
            type="button"
            className={cn(
              'flex-1 px-3 py-2 rounded-lg border text-xs font-medium transition-colors text-center',
              mode === opt
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border bg-background text-muted-foreground hover:bg-muted',
            )}
            onClick={() => setMode(opt)}
          >
            {t(`agent.routing${opt === 'global' ? 'UseGlobal' : opt === 'custom' ? 'Custom' : 'Disabled'}`)}
          </button>
        ))}
      </div>

      {mode === 'custom' && ms && (
        <div className="space-y-3 pt-2 border-t border-border/50">
          <RoutingModelSlot
            label={t('agent.routingLightModel')}
            providerId={ms.lightProviderId}
            model={ms.lightModel}
            placeholder={t('agent.routingSelectModel')}
            onSelect={(pid, m) => editor.setModelSelection({ ...ms, lightProviderId: pid, lightModel: m })}
            onClear={() => editor.setModelSelection({ ...ms, lightProviderId: undefined, lightModel: undefined })}
          />
          <RoutingModelSlot
            label={t('agent.routingReasoningModel')}
            providerId={ms.reasoningProviderId}
            model={ms.reasoningModel}
            placeholder={t('agent.routingSelectModel')}
            onSelect={(pid, m) => editor.setModelSelection({ ...ms, reasoningProviderId: pid, reasoningModel: m })}
            onClear={() =>
              editor.setModelSelection({ ...ms, reasoningProviderId: undefined, reasoningModel: undefined })
            }
          />
        </div>
      )}
    </div>
  );
}

function RoutingModelSlot({
  label,
  providerId,
  model,
  placeholder,
  onSelect,
  onClear,
}: {
  label: string;
  providerId?: string;
  model?: string;
  placeholder: string;
  onSelect: (providerId: string, model: string) => void;
  onClear: () => void;
}) {
  const selection = providerId && model ? { providerId, model } : null;

  return (
    <div>
      <label className="text-xs font-medium text-muted-foreground mb-1.5 block">{label}</label>
      <div className="flex items-center gap-2">
        <div className="flex-1">
          <ModelPickerPopover
            currentSelection={selection}
            onSelect={onSelect}
            trigger={
              <button
                type="button"
                className={cn(
                  'flex h-9 w-full items-center justify-between rounded-lg border px-3 py-2 text-sm transition-colors',
                  selection
                    ? 'border-primary/20 bg-primary/5'
                    : 'border-input bg-secondary/50 text-muted-foreground hover:bg-secondary/80',
                )}
              >
                <div className="flex items-center gap-2 min-w-0">
                  {selection && <ProviderIcon providerId={selection.providerId} size={14} />}
                  <span className="truncate">{selection?.model ?? placeholder}</span>
                </div>
                <IconChevronDown className="h-4 w-4 opacity-50 shrink-0 ml-2" />
              </button>
            }
          />
        </div>
        {selection && (
          <button
            type="button"
            onClick={onClear}
            className="flex items-center justify-center w-9 h-9 rounded-lg border border-border bg-secondary/50 hover:bg-destructive/10 hover:border-destructive/30 transition-colors flex-shrink-0 text-muted-foreground hover:text-destructive-text"
          >
            <X size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
