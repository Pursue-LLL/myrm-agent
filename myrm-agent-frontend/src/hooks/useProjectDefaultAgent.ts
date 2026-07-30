/**
 * [INPUT] @/store/useProjectStore, @/store/useAgentStore, @/store/useChatStore
 * [OUTPUT] useProjectDefaultAgent: 新建对话时自动应用项目默认智能体
 * [POS] 监听新建对话 + 项目筛选状态，自动将项目绑定的默认 Agent 注入 agentConfig。
 */

import { useEffect, useRef } from 'react';
import { useProjectStore } from '@/store/useProjectStore';
import useAgentStore from '@/store/useAgentStore';
import useChatStore from '@/store/useChatStore';
import { useSkillStore } from '@/store/skill';
import { buildAgentConfig } from '@/lib/utils/agentConfigMapper';

export function useProjectDefaultAgent(): void {
  const activeFilter = useProjectStore((s) => s.activeFilter);
  const projects = useProjectStore((s) => s.projects);
  const newChatCreated = useChatStore((s) => s.newChatCreated);
  const agentConfig = useChatStore((s) => s.agentConfig);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!newChatCreated) return;
    if (agentConfig) return;

    const project = typeof activeFilter === 'string' ? projects.find((p) => p.id === activeFilter) : undefined;
    const defaultAgentId = project?.defaultAgentId;
    if (!defaultAgentId) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    useAgentStore
      .getState()
      .fetchAgent(defaultAgentId, controller.signal)
      .then(async (agent) => {
        if (!agent || controller.signal.aborted) return;
        if (useChatStore.getState().agentConfig) return;

        const { fetchMarketSkills, fetchLocalSkills } = useSkillStore.getState();
        await Promise.all([fetchMarketSkills(true), fetchLocalSkills()]);
        if (controller.signal.aborted) return;

        useChatStore.getState().setAgentConfig(buildAgentConfig(agent));
      })
      .catch(() => {});

    return () => controller.abort();
  }, [newChatCreated, activeFilter, projects, agentConfig]);
}
