/**
 * [INPUT]
 * - next/navigation (POS: 查询参数与地址替换)
 * - @/services/agent::getAgent (POS: 读取 URL 指定的智能体)
 * - @/hooks/approval/usePendingApprovalsRecovery::fetchPendingApprovals (POS: 待审批列表)
 * - @/store/useChatStore, useConfigStore, useSkillStore, useApprovalStore (POS: 应用结果的落点)
 *
 * [OUTPUT]
 * - useChatUrlEntries: 应用并清理 URL 里的入口参数
 *   - agent_id / agentId：切到智能代理模式并应用智能体配置；用户已离开该会话则不应用；加载失败时提示并清掉参数，再点同一链接即重试
 *   - restore_arg：预填归档恢复提示与待执行动作，并聚焦输入框
 *   - approval：先清掉地址参数，再按 id 打开对应的待审批卡片（列表晚到也不会把用户拉回这个会话）
 *
 * [POS]
 * ChatWindow 的 URL 入口层。restore_arg 与 approval 要等会话消息加载完成且处于具体会话才应用，agent_id 立即应用；
 * 每个入口只应用一次，随后把地址换成不带参数的会话路由。依赖变化或 React 重放副作用都不会让同一个入口再应用一次，
 * 地址清掉参数后同一个入口再次使用则是一次新的应用。
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
import useApprovalStore, { type ApprovalPayload } from '@/store/useApprovalStore';
import useChatStore from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';

/** Lets the composer render the prefilled prompt before it takes the caret. */
const COMPOSER_FOCUS_DELAY_MS = 100;

function focusComposerAtEnd(): void {
  const input = document.querySelector('textarea');
  if (input instanceof HTMLTextAreaElement) {
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  }
}

export function useChatUrlEntries(id: string | undefined): void {
  const searchParams = useSearchParams();
  const router = useRouter();
  const t = useTranslations('agent');
  const sessionAnalyticsT = useTranslations('settings.sessionAnalytics');
  const agentIdFromUrl = searchParams.get('agent_id') ?? searchParams.get('agentId');
  const restoreArgFromUrl = searchParams.get('restore_arg');
  const approvalIdFromUrl = searchParams.get('approval');

  // Each ref holds the entry being applied or already applied; it is cleared once the address no longer carries it.
  const hasAppliedAgentRef = useRef<string | null>(null);
  const hasAppliedRestoreArgRef = useRef<string | null>(null);
  const hasAppliedApprovalRef = useRef<string | null>(null);
  const composerFocusTimerRef = useRef<number | undefined>(undefined);

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

  useEffect(() => {
    if (!restoreArgFromUrl) {
      hasAppliedRestoreArgRef.current = null;
      return;
    }
    if (!id || !isMessagesLoaded) {
      return;
    }
    if (hasAppliedRestoreArgRef.current === restoreArgFromUrl) {
      return;
    }

    hasAppliedRestoreArgRef.current = restoreArgFromUrl;
    setPendingArchiveRestoreActions([{ type: 'archive_restore', restoreArg: restoreArgFromUrl }]);
    setInputMessage(sessionAnalyticsT('contextHealth.pruning.restorePrompt', { restoreArg: restoreArgFromUrl }));
    router.replace(`/${encodeURIComponent(id)}`, { scroll: false });
    // Rewriting the address re-runs this effect, so the timer must outlive it.
    window.clearTimeout(composerFocusTimerRef.current);
    composerFocusTimerRef.current = window.setTimeout(focusComposerAtEnd, COMPOSER_FOCUS_DELAY_MS);
  }, [
    id,
    isMessagesLoaded,
    restoreArgFromUrl,
    router,
    sessionAnalyticsT,
    setInputMessage,
    setPendingArchiveRestoreActions,
  ]);

  // A pending focus belongs to the chat it was requested in.
  useEffect(() => () => window.clearTimeout(composerFocusTimerRef.current), [id]);

  useEffect(() => {
    if (!approvalIdFromUrl) {
      hasAppliedApprovalRef.current = null;
      return;
    }
    if (!id || !isMessagesLoaded) {
      return;
    }
    if (hasAppliedApprovalRef.current === approvalIdFromUrl) {
      return;
    }
    hasAppliedApprovalRef.current = approvalIdFromUrl;

    // Cleaned before the request: the list can arrive after the user has moved on, and must not pull them back here.
    router.replace(`/${encodeURIComponent(id)}`, { scroll: false });
    void (async () => {
      const approvals = await fetchPendingApprovals().catch((error: unknown): ApprovalPayload[] => {
        console.warn('Failed to load the pending approvals for the deep link', error);
        return [];
      });
      const match = approvals.find((approval) => approval.approval_id === approvalIdFromUrl);
      if (match) {
        useApprovalStore.getState().openApproval(match);
      }
    })();
  }, [approvalIdFromUrl, id, isMessagesLoaded, router]);

  // 处理 agent_id URL 参数 - 自动切换到智能代理模式并应用智能体配置
  useEffect(() => {
    if (!agentIdFromUrl) {
      hasAppliedAgentRef.current = null;
      return;
    }
    // Claimed before the first await: this effect re-runs while the agent loads and must not start a second apply.
    if (hasAppliedAgentRef.current === agentIdFromUrl) {
      return;
    }
    hasAppliedAgentRef.current = agentIdFromUrl;
    // 清除 URL 参数，避免刷新时重复应用（保留当前会话路由）；成功与失败都消耗这次入口
    const cleanAddress = id ? `/${encodeURIComponent(id)}` : '/';

    void (async () => {
      try {
        const agent = await getAgent(agentIdFromUrl);
        const { fetchMarketSkills, fetchLocalSkills } = useSkillStore.getState();
        await Promise.all([fetchMarketSkills(true), fetchLocalSkills()]);
        // The user may have opened another chat while the agent and the skill lists were loading.
        const currentChatId = useChatStore.getState().chatId;
        if (id && currentChatId && currentChatId !== id) {
          return;
        }
        const skillStore = useSkillStore.getState();
        const allSkills = [...skillStore.marketSkills, ...skillStore.localSkills];
        // 校验智能体依赖；工具配置读取校验时刻的最新值，加载期间到达的保存配置也算数
        const validation = validateAgentDependencies(agent, allSkills, useConfigStore.getState().mcpConfigs);
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
        router.replace(cleanAddress, { scroll: false });
      } catch (error) {
        console.warn('Failed to load the agent configuration', error);
        toast({ title: t('loadAgentFailed'), variant: 'destructive' });
        router.replace(cleanAddress, { scroll: false });
      }
    })();
  }, [agentIdFromUrl, id, setActionMode, setAgentConfig, router, t]);
}
