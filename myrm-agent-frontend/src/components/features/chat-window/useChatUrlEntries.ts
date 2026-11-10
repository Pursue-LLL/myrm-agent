/**
 * [INPUT]
 * - next/navigation (POS: 查询参数与地址替换)
 * - @/services/agent::getAgent (POS: 读取 URL 指定的智能体)
 * - @/hooks/approval/usePendingApprovalsRecovery::fetchPendingApprovals (POS: 待审批列表)
 * - @/store/useChatStore, useConfigStore, useSkillStore, useApprovalStore (POS: 应用结果的落点)
 *
 * [OUTPUT]
 * - useChatUrlEntries: 应用并清理 URL 里的入口参数
 *   - agent_id / agentId：切到智能代理模式并应用智能体配置
 *   - restore_arg：预填归档恢复提示与待执行动作，并聚焦输入框
 *   - approval：打开对应的待审批卡片
 *
 * [POS]
 * ChatWindow 的 URL 入口层。每个入口在会话消息加载完成后应用一次，随后把地址换成不带参数的会话路由，
 * 刷新页面不会重复应用。
 */

import { useEffect, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';
import { fetchPendingApprovals } from '@/hooks/approval/usePendingApprovalsRecovery';
import { toast } from '@/hooks/shared/useToast';
import { buildAgentConfig, buildMissingDependenciesParts, validateAgentDependencies } from '@/lib/utils/agent-config';
import { getAgent } from '@/services/agent';
import { useSkillStore } from '@/store/skill';
import useApprovalStore from '@/store/useApprovalStore';
import useChatStore from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';

export function useChatUrlEntries(id: string | undefined): void {
  const searchParams = useSearchParams();
  const router = useRouter();
  const t = useTranslations('agent');
  const sessionAnalyticsT = useTranslations('settings.sessionAnalytics');
  const agentIdFromUrl = searchParams.get('agent_id') ?? searchParams.get('agentId');
  const restoreArgFromUrl = searchParams.get('restore_arg');
  const approvalIdFromUrl = searchParams.get('approval');
  const hasAppliedAgentRef = useRef<string | null>(null);
  const hasAppliedRestoreArgRef = useRef<string | null>(null);
  const hasAppliedApprovalRef = useRef<string | null>(null);

  const { isMessagesLoaded, setActionMode, setAgentConfig, setInputMessage, setPendingArchiveRestoreActions } =
    useChatStore(
      useShallow((state) => ({
        isMessagesLoaded: state.isMessagesLoaded,
        setActionMode: state.setActionMode,
        setAgentConfig: state.setAgentConfig,
        setInputMessage: state.setInputMessage,
        setPendingArchiveRestoreActions: state.setPendingArchiveRestoreActions,
      })),
    );
  const mcpConfigs = useConfigStore((state) => state.mcpConfigs);

  useEffect(() => {
    if (!id || !restoreArgFromUrl || !isMessagesLoaded) {
      return;
    }
    const restoreKey = `${id}:${restoreArgFromUrl}`;
    if (hasAppliedRestoreArgRef.current === restoreKey) {
      return;
    }

    hasAppliedRestoreArgRef.current = restoreKey;
    setPendingArchiveRestoreActions([{ type: 'archive_restore', restoreArg: restoreArgFromUrl }]);
    setInputMessage(sessionAnalyticsT('contextHealth.pruning.restorePrompt', { restoreArg: restoreArgFromUrl }));
    router.replace(`/${encodeURIComponent(id)}`, { scroll: false });
    const focusTimer = window.setTimeout(() => {
      if (typeof document === 'undefined') {
        return;
      }
      const inputElement = document.querySelector('textarea');
      if (inputElement instanceof HTMLTextAreaElement) {
        inputElement.focus();
        inputElement.setSelectionRange(inputElement.value.length, inputElement.value.length);
      }
    }, 100);
    return () => {
      window.clearTimeout(focusTimer);
    };
  }, [
    id,
    isMessagesLoaded,
    restoreArgFromUrl,
    router,
    sessionAnalyticsT,
    setInputMessage,
    setPendingArchiveRestoreActions,
  ]);

  useEffect(() => {
    if (!id || !approvalIdFromUrl || !isMessagesLoaded) {
      return;
    }
    const approvalKey = `${id}:${approvalIdFromUrl}`;
    if (hasAppliedApprovalRef.current === approvalKey) {
      return;
    }
    hasAppliedApprovalRef.current = approvalKey;

    void (async () => {
      const approvals = await fetchPendingApprovals();
      const match = approvals.find((approval) => approval.approval_id === approvalIdFromUrl);
      if (match) {
        useApprovalStore.getState().openApproval(match);
      }
      router.replace(`/${encodeURIComponent(id)}`, { scroll: false });
    })();
  }, [approvalIdFromUrl, id, isMessagesLoaded, router]);

  // 处理 agent_id URL 参数 - 自动切换到智能代理模式并应用智能体配置
  useEffect(() => {
    if (!agentIdFromUrl) {
      return;
    }
    // 避免重复应用同一个智能体
    if (hasAppliedAgentRef.current === agentIdFromUrl) {
      return;
    }

    const applyAgentConfig = async () => {
      try {
        const agent = await getAgent(agentIdFromUrl);
        if (agent) {
          const currentChatId = useChatStore.getState().chatId;
          if (id && currentChatId && currentChatId !== id) {
            return;
          }
          const { fetchMarketSkills, fetchLocalSkills } = useSkillStore.getState();
          await Promise.all([fetchMarketSkills(true), fetchLocalSkills()]);
          const skillStore = useSkillStore.getState();
          const allSkills = [...skillStore.marketSkills, ...skillStore.localSkills];
          // 校验智能体依赖
          const validation = validateAgentDependencies(agent, allSkills, mcpConfigs);
          if (!validation.isValid) {
            const missingParts = buildMissingDependenciesParts(validation);
            const partsText = missingParts.map((p) => t(p.key, { count: p.count })).join('、');
            toast({
              title: t('validation.dependencyInvalid'),
              description: `${partsText}。${t('validation.pleaseEdit')}`,
              variant: 'destructive',
            });
          }

          // 切换到智能代理模式
          setActionMode('agent');

          // 应用智能体配置：与会话恢复共用同一 Agent→AgentConfig 映射，
          // 内置工具、模型选择、MCP 工具选择等字段不会在 URL 入口被遗漏
          setAgentConfig(buildAgentConfig(agent));

          // 标记已应用
          hasAppliedAgentRef.current = agentIdFromUrl;

          // 清除 URL 参数，避免刷新时重复应用（保留当前会话路由）
          const nextPath = id ? `/${encodeURIComponent(id)}` : '/';
          router.replace(nextPath, { scroll: false });
        }
      } catch (error) {
        console.warn('加载智能体配置失败:', error);
      }
    };

    applyAgentConfig();
  }, [agentIdFromUrl, id, setActionMode, setAgentConfig, router, mcpConfigs, t]);
}
