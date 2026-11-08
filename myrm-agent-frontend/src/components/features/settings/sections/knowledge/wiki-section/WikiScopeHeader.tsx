'use client';

/**
 * [INPUT] @/components/primitives/select (POS: 下拉选择), @/components/agent/builtin-agent-i18n::getBuiltinAgentName (POS: 内置智能体的本地化名称)
 * [OUTPUT] WikiScopeHeader: Wiki 面板的标题、说明与智能体范围选择器 (含默认范围, 加载智能体列表时禁用) 以及范围提示
 * [POS] Wiki 面板顶部的范围切换区; 选择值 'default' 代表不带 agentId 的默认范围。
 */

import { useLocale, useTranslations } from 'next-intl';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import type { AgentListItem } from '@/services/agent';

interface WikiScopeHeaderProps {
  agentScopeId: string | null;
  agents: AgentListItem[];
  agentsLoading: boolean;
  onScopeChange: (value: string) => void;
}

export function WikiScopeHeader({ agentScopeId, agents, agentsLoading, onScopeChange }: WikiScopeHeaderProps) {
  const t = useTranslations('settings.wiki');
  const locale = useLocale();

  return (
    <div>
      <h2 className="text-2xl font-semibold mb-2">{t('title')}</h2>
      <p className="text-muted-foreground">{t('description')}</p>
      <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:gap-3">
          <span className="text-sm font-medium text-foreground">{t('agentScopeLabel')}</span>
          <Select value={agentScopeId ?? 'default'} onValueChange={onScopeChange} disabled={agentsLoading}>
            <SelectTrigger className="w-full sm:w-72">
              <SelectValue placeholder={agentsLoading ? t('loading') : t('agentScopePlaceholder')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="default">{t('agentScopeDefault')}</SelectItem>
              {agents.map((agent) => (
                <SelectItem key={agent.id} value={agent.id}>
                  {getBuiltinAgentName(agent.id, agent.name, locale)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <p className="text-sm text-primary/80">{agentScopeId ? t('agentScopeNotice') : t('defaultScopeNotice')}</p>
      </div>
    </div>
  );
}
