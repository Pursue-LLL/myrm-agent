'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Zap } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { getConfigSyncManager, type ExternalAgentConfig } from '@/services/config';
import useChatStore from '@/store/useChatStore';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';

/**
 * 直连外部 Agent 选择器
 *
 * 从外部 agent 配置中读取已启用的 agent 列表，
 * 让用户选择后绕过主 LLM 直接路由到指定外部 agent。
 */
const DirectDelegateSelector = memo(() => {
  const t = useTranslations('agent.configPanel');
  const [agents, setAgents] = useState<ExternalAgentConfig[]>([]);
  const agentConfig = useChatStore((state) => state.agentConfig);
  const updateAgentConfig = useChatStore((state) => state.updateAgentConfig);

  useEffect(() => {
    const syncManager = getConfigSyncManager();
    const val = syncManager.get('externalAgents');
    if (val?.agents) {
      setAgents(val.agents.filter((a) => a.enabled));
    }
  }, []);

  const selected = agentConfig?.forceExternalAgent || '__off__';

  const handleChange = useCallback(
    (value: string) => {
      updateAgentConfig({ forceExternalAgent: value === '__off__' ? undefined : value });
    },
    [updateAgentConfig],
  );

  if (agents.length === 0) {
    return null;
  }

  return (
    <div className="flex items-center gap-2 mt-3">
      <Zap size={14} className="text-amber-500 flex-shrink-0" />
      <span className="text-xs text-muted-foreground whitespace-nowrap">{t('directDelegate')}</span>
      <Select value={selected} onValueChange={handleChange}>
        <SelectTrigger
          className={cn(
            'flex-1 min-w-0 h-7 text-xs px-2 rounded-full border-border/50',
            selected !== '__off__' && 'border-amber-400/50 bg-amber-50/30 dark:bg-amber-950/20',
          )}
        >
          <SelectValue placeholder={t('directDelegateOff')} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__off__">{t('directDelegateOff')}</SelectItem>
          {agents.map((a) => (
            <SelectItem key={a.name} value={a.name}>
              {a.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
});
DirectDelegateSelector.displayName = 'DirectDelegateSelector';

export default DirectDelegateSelector;
