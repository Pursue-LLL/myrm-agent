/**
 * [INPUT] @/services/cron::checkCronPrerequisite (POS: 前置验证查询), ./cronCreateModel (POS: 默认 Agent / 无模板哨兵值)
 * [OUTPUT] useCronPrerequisite: 去抖的前置验证状态 { stats, loading, clear }
 * [POS] 创建弹窗的“是否已手动验证过”门禁数据层：内容停止变化 400ms 后才查询；没有可查询的内容时清空结果，查询失败视为无结果；clear 供弹窗重置时使用。
 */

import { useCallback, useEffect, useState } from 'react';
import { checkCronPrerequisite, type PrerequisiteCheckResponse } from '@/services/cron';
import { DEFAULT_AGENT_ID, NO_WORKFLOW_TEMPLATE } from './cronCreateModel';

const DEBOUNCE_MS = 400;

interface PrerequisiteParams {
  enabled: boolean;
  prompt: string;
  command: string;
  agentId: string;
  workflowTemplateId: string;
  chatId: string | null;
}

export function useCronPrerequisite({
  enabled,
  prompt,
  command,
  agentId,
  workflowTemplateId,
  chatId,
}: PrerequisiteParams) {
  const [stats, setStats] = useState<PrerequisiteCheckResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    const timer = setTimeout(() => {
      if (!prompt && !command) {
        setStats(null);
        return;
      }
      setLoading(true);
      void checkCronPrerequisite({
        prompt: prompt || undefined,
        command: command || undefined,
        agent_id: agentId !== DEFAULT_AGENT_ID ? agentId : undefined,
        workflow_template_id: workflowTemplateId !== NO_WORKFLOW_TEMPLATE ? workflowTemplateId : undefined,
        chat_id: chatId ?? undefined,
      })
        .then(setStats)
        .catch(() => setStats(null))
        .finally(() => setLoading(false));
    }, DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [enabled, prompt, command, agentId, workflowTemplateId, chatId]);

  const clear = useCallback(() => {
    setStats(null);
    setLoading(false);
  }, []);

  return { stats, loading, clear };
}
