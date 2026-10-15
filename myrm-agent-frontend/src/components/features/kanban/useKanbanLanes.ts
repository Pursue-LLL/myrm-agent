/**
 * [INPUT]
 * - 无项目内依赖（仅 React 状态与 localStorage）
 *
 * [OUTPUT]
 * - useKanbanLanes: Running 列「按 Agent 分泳道」开关（记在 localStorage）与泳道折叠状态
 *
 * [POS]
 * 看板泳道的状态层。关闭泳道时同时清空折叠记录；分组与可见卡片的规则在 kanban-selection.ts。
 */
'use client';

import { useCallback, useState } from 'react';

export function useKanbanLanes() {
  const [laneByProfile, setLaneByProfile] = useState<boolean>(() => {
    if (typeof window === 'undefined') {
      return true;
    }
    try {
      return localStorage.getItem('kanban_lane_by_profile') !== 'false';
    } catch {
      return true;
    }
  });
  const [collapsedAgents, setCollapsedAgents] = useState<Set<string>>(new Set());

  const toggleLaneByProfile = useCallback(() => {
    setLaneByProfile((prev) => {
      const next = !prev;
      try {
        localStorage.setItem('kanban_lane_by_profile', String(next));
      } catch {
        /* ignore */
      }
      if (!next) {
        setCollapsedAgents(new Set());
      }
      return next;
    });
  }, []);

  const toggleAgentCollapse = useCallback((agentKey: string) => {
    setCollapsedAgents((prev) => {
      const next = new Set(prev);
      if (next.has(agentKey)) {
        next.delete(agentKey);
      } else {
        next.add(agentKey);
      }
      return next;
    });
  }, []);

  return { laneByProfile, collapsedAgents, toggleLaneByProfile, toggleAgentCollapse };
}
