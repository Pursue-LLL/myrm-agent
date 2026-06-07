'use client';

import { useState, useEffect } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { IconPlus, IconX, IconBot } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { getBuiltinAgentName, getBuiltinAgentDescription } from '@/components/agent/builtin-agent-i18n';
import { listAgents, type AgentListItem } from '@/services/agent';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';

interface AgentSubagentBindingProps {
  selectedIds: string[];
  currentAgentId: string | null;
  onChange: (ids: string[]) => void;
}

export function AgentSubagentBinding({ selectedIds, currentAgentId, onChange }: AgentSubagentBindingProps) {
  const t = useTranslations('agent');
  const locale = useLocale();
  const [agents, setAgents] = useState<AgentListItem[]>([]);
  const [popoverOpen, setPopoverOpen] = useState(false);

  useEffect(() => {
    listAgents(1, 100)
      .then((res) => setAgents(res.items))
      .catch(() => setAgents([]));
  }, []);

  const availableAgents = agents.filter((a) => a.id !== currentAgentId && !selectedIds.includes(a.id));

  const selectedAgents = selectedIds.map((id) => agents.find((a) => a.id === id)).filter(Boolean) as AgentListItem[];

  const handleAdd = (agentId: string) => {
    onChange([...selectedIds, agentId]);
    setPopoverOpen(false);
  };

  const handleRemove = (agentId: string) => {
    onChange(selectedIds.filter((id) => id !== agentId));
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

      <div className="space-y-2">
        {selectedAgents.length === 0 && <p className="text-xs text-muted-foreground italic py-2">{t('noSubagents')}</p>}

        {selectedAgents.map((agent) => (
          <div
            key={agent.id}
            className={cn(
              'flex items-center justify-between px-3 py-2 rounded-lg',
              'bg-secondary/50 border border-border/50',
            )}
          >
            <div className="flex items-center gap-2 min-w-0">
              <IconBot className="w-3.5 h-3.5 text-violet-500 shrink-0" />
              <span className="text-sm truncate">{getBuiltinAgentName(agent.id, agent.name, locale)}</span>
              {agent.description && (
                <span className="text-xs text-muted-foreground truncate hidden sm:inline">
                  {getBuiltinAgentDescription(agent.id, agent.description, locale)}
                </span>
              )}
            </div>
            <button
              onClick={() => handleRemove(agent.id)}
              className="text-muted-foreground hover:text-destructive transition-colors ml-2 shrink-0"
              title={t('removeSubagent')}
            >
              <IconX className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}

        <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm" className="w-full gap-2 rounded-lg border-dashed">
              <IconPlus className="w-3.5 h-3.5" />
              {t('addSubagent')}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-72 p-2" align="start">
            {availableAgents.length === 0 ? (
              <p className="text-xs text-muted-foreground p-2 text-center">{t('noSubagents')}</p>
            ) : (
              <div className="max-h-60 overflow-y-auto space-y-1">
                {availableAgents.map((agent) => (
                  <button
                    key={agent.id}
                    onClick={() => handleAdd(agent.id)}
                    className={cn(
                      'w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left',
                      'hover:bg-accent transition-colors text-sm',
                    )}
                  >
                    <IconBot className="w-3.5 h-3.5 text-violet-500 shrink-0" />
                    <div className="min-w-0">
                      <div className="truncate font-medium">{getBuiltinAgentName(agent.id, agent.name, locale)}</div>
                      {agent.description && (
                        <div className="text-xs text-muted-foreground truncate">
                          {getBuiltinAgentDescription(agent.id, agent.description, locale)}
                        </div>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </PopoverContent>
        </Popover>
      </div>
    </div>
  );
}
