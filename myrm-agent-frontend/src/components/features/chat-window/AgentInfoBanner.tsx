'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Settings, ChevronDown, Check } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { AgentAvatar } from '@/components/agent/AgentAvatar';
import { getBuiltinAgentName, getBuiltinAgentDescription } from '@/components/agent/builtin-agent-i18n';
import { getAgent, type Agent } from '@/services/agent';
import { buildAgentConfig } from '@/lib/utils/agentConfigMapper';
import useAgentStore from '@/store/useAgentStore';
import useChatStore from '@/store/useChatStore';
import { toast } from '@/hooks/useToast';

interface AgentInfoBannerProps {
  agentId: string;
  className?: string;
}

export default function AgentInfoBanner({ agentId, className }: AgentInfoBannerProps) {
  const router = useRouter();
  const locale = useLocale();
  const t = useTranslations('agent.configPanel');
  const [agent, setAgent] = useState<Agent | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [switchOpen, setSwitchOpen] = useState(false);
  const agents = useAgentStore((s) => s.agents);
  const fetchAgents = useAgentStore((s) => s.fetchAgents);
  const isStreaming = useChatStore((s) => s.loading);

  useEffect(() => {
    let stale = false;
    const loadAgent = async () => {
      try {
        const data = await getAgent(agentId);
        if (!stale) setAgent(data);
      } catch {
        if (!stale) setAgent(null);
      } finally {
        if (!stale) setInitialLoading(false);
      }
    };
    loadAgent();
    return () => { stale = true; };
  }, [agentId]);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  const handleSwitchAgent = useCallback(
    async (targetAgentId: string) => {
      if (targetAgentId === agentId) {
        setSwitchOpen(false);
        return;
      }

      try {
        const fullAgent = await getAgent(targetAgentId);
        if (!fullAgent) return;

        useChatStore.getState().setAgentConfig(buildAgentConfig(fullAgent));
        setAgent(fullAgent);
        toast({ title: t('updateSuccess'), description: getBuiltinAgentName(fullAgent.id, fullAgent.name, locale) });
      } catch {
        toast({ title: t('switchFailed'), variant: 'destructive' });
      } finally {
        setSwitchOpen(false);
      }
    },
    [agentId, locale, t],
  );

  if (initialLoading || !agent) return null;

  return (
    <div className={cn('flex items-center gap-3 px-4 py-2 bg-muted/50 border-b border-border', className)}>
      <AgentAvatar url={agent.avatar_url} name={agent.name} agentId={agent.id} size="sm" />

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{getBuiltinAgentName(agent.id, agent.name, locale)}</p>
        {agent.description && (
          <p className="text-xs text-muted-foreground truncate">
            {getBuiltinAgentDescription(agent.id, agent.description, locale)}
          </p>
        )}
        {agent.enabled_builtin_tools?.includes('wiki') && (
          <p className="text-xs text-primary/80 truncate">{t('wikiActiveIndicator')}</p>
        )}
      </div>

      <Popover open={switchOpen} onOpenChange={setSwitchOpen}>
        <PopoverTrigger asChild>
          <Button variant="ghost" size="sm" disabled={isStreaming} className="flex items-center gap-1">
            <ChevronDown className="w-4 h-4" />
            <span className="hidden sm:inline">{t('switchButton')}</span>
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[240px] p-1" align="end">
          <div className="flex flex-col max-h-[300px] overflow-y-auto">
            {agents.map((item) => (
              <div
                key={item.id}
                className={cn(
                  'relative flex cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-1.5 text-sm',
                  'hover:bg-accent hover:text-accent-foreground',
                  item.id === agentId ? 'bg-accent/50' : '',
                )}
                onClick={() => handleSwitchAgent(item.id)}
              >
                <AgentAvatar url={item.avatar_url} name={item.name} agentId={item.id} size="sm" className="h-6 w-6" />
                <span className="flex-1 truncate">{getBuiltinAgentName(item.id, item.name, locale)}</span>
                {item.id === agentId && <Check className="h-4 w-4 shrink-0 text-primary" />}
              </div>
            ))}
          </div>
        </PopoverContent>
      </Popover>

      <Button
        variant="ghost"
        size="sm"
        onClick={() => router.push(`/settings?tab=wiki&agentId=${encodeURIComponent(agent.id)}`)}
        className="flex items-center gap-1"
      >
        <Settings className="w-4 h-4" />
      </Button>
    </div>
  );
}
