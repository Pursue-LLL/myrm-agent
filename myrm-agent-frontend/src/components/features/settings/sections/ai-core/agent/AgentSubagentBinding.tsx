'use client';

import { useEffect, useMemo, useState } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { IconPlus, IconX, IconBot } from '@/components/features/icons/PremiumIcons';
import { AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { getBuiltinAgentName, getBuiltinAgentDescription } from '@/components/agent/builtin-agent-i18n';
import { getSubagentPresets, listAgents, type AgentListItem, type SubagentPresetItem } from '@/services/agent';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';

interface AgentSubagentBindingProps {
  selectedIds: string[];
  currentAgentId: string | null;
  onChange: (ids: string[]) => void;
  enabledBuiltinTools?: string[];
  onOpenBuiltinTools?: () => void;
  showRebindHint?: boolean;
  onDismissRebindHint?: () => void;
}

interface SelectedItem {
  id: string;
  name: string;
  description: string;
  isPreset: boolean;
  requiredBuiltinTools: string[];
}

type TranslateAgent = (key: string) => string;

function presetName(t: TranslateAgent, preset: SubagentPresetItem): string {
  return t(`subagentPresets.${preset.id}.name`);
}

function presetDescription(t: TranslateAgent, preset: SubagentPresetItem): string {
  return t(`subagentPresets.${preset.id}.description`);
}

export function AgentSubagentBinding({
  selectedIds,
  currentAgentId,
  onChange,
  enabledBuiltinTools = [],
  onOpenBuiltinTools,
  showRebindHint = false,
  onDismissRebindHint,
}: AgentSubagentBindingProps) {
  const t = useTranslations('agent');
  const tNotifications = useTranslations('notifications');
  const locale = useLocale();
  const [agents, setAgents] = useState<AgentListItem[]>([]);
  const [presets, setPresets] = useState<SubagentPresetItem[]>([]);
  const [catalogLoaded, setCatalogLoaded] = useState(false);
  const [popoverOpen, setPopoverOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([listAgents(1, 100), getSubagentPresets()]).then(([agentResult, presetResult]) => {
      if (cancelled) {
        return;
      }
      if (agentResult.status === 'fulfilled') {
        setAgents(agentResult.value.items);
      }
      if (presetResult.status === 'fulfilled') {
        setPresets(presetResult.value);
      }
      setCatalogLoaded(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedItems = useMemo(() => {
    const presetById = new Map(presets.map((preset) => [preset.id, preset]));
    const agentById = new Map(agents.map((agent) => [agent.id, agent]));
    return selectedIds.map((id): SelectedItem => {
      const preset = presetById.get(id);
      if (preset) {
        return {
          id,
          name: presetName(t, preset),
          description: presetDescription(t, preset),
          isPreset: true,
          requiredBuiltinTools: preset.required_builtin_tools,
        };
      }
      const agent = agentById.get(id);
      if (agent) {
        return {
          id,
          name: getBuiltinAgentName(agent.id, agent.name, locale),
          description: getBuiltinAgentDescription(agent.id, agent.description || '', locale),
          isPreset: false,
          requiredBuiltinTools: [],
        };
      }
      return {
        id,
        name: t('subagentUnavailable'),
        description: t('subagentUnavailableDesc'),
        isPreset: false,
        requiredBuiltinTools: [],
      };
    });
  }, [agents, locale, presets, selectedIds, t]);

  const availablePresets = presets.filter((preset) => !selectedIds.includes(preset.id));
  const availableAgents = agents.filter((agent) => agent.id !== currentAgentId && !selectedIds.includes(agent.id));
  const missingBuiltinTools = selectedItems.flatMap((item) =>
    item.requiredBuiltinTools.filter((tool) => !enabledBuiltinTools.includes(tool)),
  );
  const uniqueMissingBuiltinTools = [...new Set(missingBuiltinTools)];

  const handleAdd = (id: string) => {
    onChange([...selectedIds, id]);
    setPopoverOpen(false);
  };

  const handleRemove = (id: string) => {
    onChange(selectedIds.filter((selectedId) => selectedId !== id));
  };

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3">
        <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
          <IconBot className="w-4 h-4 text-violet-500" />
          {t('subagentBinding')}
        </h3>
        <p className="text-xs text-muted-foreground mt-0.5">{t('subagentBindingDesc')}</p>
      </div>

      {showRebindHint && (
        <output
          className={cn(
            'mb-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2',
            'dark:border-amber-900/50 dark:bg-amber-950/30',
          )}
        >
          <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
          <span className="text-xs text-amber-900 dark:text-amber-100 flex-1">
            {tNotifications('subagentRebindRequired')}
          </span>
          {onDismissRebindHint && (
            <button
              type="button"
              onClick={onDismissRebindHint}
              className="text-xs text-amber-700 dark:text-amber-300 hover:underline shrink-0"
            >
              {t('dismissRebindHint')}
            </button>
          )}
        </output>
      )}

      <div className="space-y-2">
        {!catalogLoaded && selectedIds.length > 0 ? (
          <div className="h-10 animate-pulse rounded-lg bg-muted/50" aria-hidden />
        ) : (
          <>
            {selectedItems.length === 0 && (
              <p className="text-xs text-muted-foreground italic py-2">{t('noSubagents')}</p>
            )}

            {selectedItems.map((item) => (
              <div
                key={item.id}
                className={cn(
                  'flex items-start justify-between gap-3 px-3 py-2 rounded-lg',
                  'bg-secondary/50 border border-border/50',
                )}
              >
                <div className="flex items-start gap-2 min-w-0">
                  <IconBot className="w-3.5 h-3.5 text-violet-500 shrink-0 mt-0.5" />
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-sm truncate">{item.name}</span>
                      {item.isPreset && (
                        <span className="shrink-0 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                          {t('builtinSpecialistBadge')}
                        </span>
                      )}
                    </div>
                    {item.description && (
                      <p className="text-xs text-muted-foreground line-clamp-2">{item.description}</p>
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => handleRemove(item.id)}
                  className="text-muted-foreground hover:text-destructive transition-colors shrink-0"
                  title={t('removeSubagent')}
                >
                  <IconX className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </>
        )}

        {uniqueMissingBuiltinTools.length > 0 && (
          <output className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-900/50 dark:bg-amber-950/30">
            <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
            <span className="flex-1">
              <span className="block text-xs text-amber-900 dark:text-amber-100">
                {t('subagentMissingBuiltinTool')}
              </span>
              {onOpenBuiltinTools && (
                <button
                  type="button"
                  onClick={onOpenBuiltinTools}
                  className="mt-1 text-xs font-medium text-amber-700 hover:underline dark:text-amber-300"
                >
                  {t('subagentEnableBuiltinTool')}
                </button>
              )}
            </span>
          </output>
        )}

        <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm" className="w-full gap-2 rounded-lg border-dashed">
              <IconPlus className="w-3.5 h-3.5" />
              {t('addSubagent')}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[min(20rem,calc(100vw-2rem))] p-2" align="start" collisionPadding={12}>
            <div className="max-h-72 overflow-y-auto space-y-1">
              {availablePresets.length > 0 && (
                <>
                  <div className="px-2 pt-1 pb-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                    {t('builtinSpecialistsGroup')}
                  </div>
                  {availablePresets.map((preset) => (
                    <button
                      key={preset.id}
                      type="button"
                      onClick={() => handleAdd(preset.id)}
                      className={cn(
                        'w-full flex items-start gap-2 px-3 py-2 rounded-lg text-left',
                        'hover:bg-accent transition-colors text-sm',
                      )}
                    >
                      <IconBot className="w-3.5 h-3.5 text-violet-500 shrink-0 mt-0.5" />
                      <div className="min-w-0">
                        <div className="truncate font-medium">{presetName(t, preset)}</div>
                        <div className="text-xs text-muted-foreground line-clamp-2">{presetDescription(t, preset)}</div>
                      </div>
                    </button>
                  ))}
                </>
              )}

              {availableAgents.length > 0 && (
                <>
                  <div className="px-2 pt-2 pb-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                    {t('myAgentsGroup')}
                  </div>
                  {availableAgents.map((agent) => (
                    <button
                      key={agent.id}
                      type="button"
                      onClick={() => handleAdd(agent.id)}
                      className={cn(
                        'w-full flex items-start gap-2 px-3 py-2 rounded-lg text-left',
                        'hover:bg-accent transition-colors text-sm',
                      )}
                    >
                      <IconBot className="w-3.5 h-3.5 text-violet-500 shrink-0 mt-0.5" />
                      <div className="min-w-0">
                        <div className="truncate font-medium">{getBuiltinAgentName(agent.id, agent.name, locale)}</div>
                        {agent.description && (
                          <div className="text-xs text-muted-foreground line-clamp-2">
                            {getBuiltinAgentDescription(agent.id, agent.description, locale)}
                          </div>
                        )}
                      </div>
                    </button>
                  ))}
                </>
              )}

              {availablePresets.length === 0 && availableAgents.length === 0 && (
                <p className="text-xs text-muted-foreground p-2 text-center">{t('noSubagents')}</p>
              )}
            </div>
          </PopoverContent>
        </Popover>
      </div>
    </div>
  );
}
