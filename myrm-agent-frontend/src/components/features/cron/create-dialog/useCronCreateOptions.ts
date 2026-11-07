/**
 * [INPUT] @/lib/api::apiRequest (POS: 部署模式探测), @/services/channels::listChannelStatuses (POS: 已连接渠道), @/services/workflowTemplates::fetchWorkflowTemplates (POS: 可绑定的工作流模板), @/store/useAgentStore (POS: Agent 列表刷新), ../CronDeliveryEditors::needsDeliveryTarget (POS: 内置渠道判定)
 * [OUTPUT] useCronCreateOptions: 弹窗打开期间从服务端取回的选项——Shell 是否可用、已连接的 IM 渠道、可绑定的工作流模板
 * [POS] 创建弹窗的只读选项层：打开时刷新 Agent 列表并探测部署模式，渠道在每次打开时重取，工作流模板仅在 Agent 类型下加载；任一请求失败都退化为“无该选项”。
 */

import { useEffect, useState } from 'react';
import { apiRequest } from '@/lib/api';
import { listChannelStatuses } from '@/services/channels';
import { fetchWorkflowTemplates, type WorkflowTemplateSummary } from '@/services/workflowTemplates';
import useAgentStore from '@/store/useAgentStore';
import { needsDeliveryTarget } from '../CronDeliveryEditors';
import type { UIJobMode } from './cronCreateModel';

export function useCronCreateOptions(open: boolean, uiMode: UIJobMode) {
  const { fetchAgents } = useAgentStore();
  /** null until the deploy mode is known; a sandbox deployment cannot run shell jobs. */
  const [shellEnabled, setShellEnabled] = useState<boolean | null>(null);
  const [connectedChannels, setConnectedChannels] = useState<string[]>([]);
  const [workflowTemplates, setWorkflowTemplates] = useState<WorkflowTemplateSummary[]>([]);

  useEffect(() => {
    if (open) {
      listChannelStatuses()
        .then((statuses) =>
          setConnectedChannels(
            statuses
              .filter((status) => status.status === 'running' && needsDeliveryTarget(status.name))
              .map((status) => status.name),
          ),
        )
        .catch(() => setConnectedChannels([]));
    }
  }, [open]);

  useEffect(() => {
    if (open && uiMode === 'agent') {
      void fetchWorkflowTemplates()
        .then((response) => setWorkflowTemplates(response.templates.filter((template) => template.trust_latch)))
        .catch(() => setWorkflowTemplates([]));
    }
  }, [open, uiMode]);

  useEffect(() => {
    if (open) {
      fetchAgents();
      apiRequest<{ deploy_mode: string }>('/health/info')
        .then((info) => setShellEnabled(info.deploy_mode !== 'sandbox'))
        .catch(() => setShellEnabled(false));
    }
  }, [open, fetchAgents]);

  return { shellEnabled, connectedChannels, workflowTemplates };
}
