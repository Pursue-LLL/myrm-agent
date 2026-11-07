/**
 * [INPUT] next/navigation (POS: ?agentId= 范围参数与路由), @/services/agent::listAgents (POS: 智能体列表), @/components/agent/builtin-agent-i18n (POS: 内置智能体的本地化名称)
 * [OUTPUT] useWikiScope: 当前智能体范围 (agentScopeId / 证据上下文键 / 范围名称)、可选智能体列表、范围修订号, 以及切换范围与前往知识图谱的动作
 * [POS] Wiki 面板的范围层: 范围只由 URL 的 agentId 决定, 每次范围变化修订号加一, 让按范围缓存的子面板重新挂载。
 */

import { useCallback, useEffect, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useLocale, useTranslations } from 'next-intl';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import { listAgents, type AgentListItem } from '@/services/agent';

export function useWikiScope() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const locale = useLocale();
  const t = useTranslations('settings.wiki');
  const agentScopeId = searchParams.get('agentId');
  const evidenceContextKey = agentScopeId ? `agent:${agentScopeId}` : 'agent:default';
  const [agents, setAgents] = useState<AgentListItem[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [scopeRevision, setScopeRevision] = useState(0);

  useEffect(() => {
    listAgents(1, 100)
      .then((res) => setAgents(res.items))
      .catch(() => setAgents([]))
      .finally(() => setAgentsLoading(false));
  }, []);

  useEffect(() => {
    setScopeRevision((revision) => revision + 1);
  }, [agentScopeId]);

  const scopeLabel = agentScopeId
    ? getBuiltinAgentName(agentScopeId, agents.find((agent) => agent.id === agentScopeId)?.name ?? agentScopeId, locale)
    : t('agentScopeDefault');

  const goToKnowledgeGraph = useCallback(() => {
    const params = new URLSearchParams({ tab: 'graph' });
    if (agentScopeId) {
      params.set('agentId', agentScopeId);
    }
    router.push(`/library?${params.toString()}`);
  }, [agentScopeId, router]);

  const handleAgentScopeChange = (value: string) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value === 'default') {
      params.delete('agentId');
    } else {
      params.set('agentId', value);
    }
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname);
  };

  return {
    agentScopeId,
    evidenceContextKey,
    agents,
    agentsLoading,
    scopeLabel,
    scopeRevision,
    goToKnowledgeGraph,
    handleAgentScopeChange,
  };
}
