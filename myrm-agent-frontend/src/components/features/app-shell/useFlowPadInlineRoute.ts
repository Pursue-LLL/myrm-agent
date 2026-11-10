/**
 * [INPUT]
 * - useAgentStore (POS: 可用 agent 列表与详情加载)
 * - buildAgentConfig (POS: agent 详情转请求级路由配置)
 * - getBuiltinAgentName (POS: 内置 agent 名本地化)
 *
 * [OUTPUT]
 * - InlineRouteSelection: 请求级路由覆盖（目标 agent 与其配置）。
 * - useFlowPadInlineRoute: 路由选择/切换状态机、可用 agent 列表、当前路由标签与菜单开合。
 *
 * [POS]
 * FlowPad Inline 的请求级路由层。切换以 AbortController 隔离晚到响应；目标不在名单内时回落到会话路由。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import { toast } from '@/lib/utils/toast';
import { buildAgentConfig } from '@/lib/utils/agent-config';
import useAgentStore from '@/store/useAgentStore';
import type { FlowPadMode } from '@/store/useFlowPadStore';
import type { AgentConfig } from '@/store/chat/types';

export interface InlineRouteSelection {
  id: string;
  name: string;
  avatarUrl?: string;
  config: AgentConfig;
}

interface UseFlowPadInlineRouteOptions {
  isOpen: boolean;
  mode: FlowPadMode;
  /** Route of the current chat session; used while no override is selected. */
  agentConfig: AgentConfig | null;
  /** Called whenever the route changes hands, so a summon is not credited to another agent. */
  clearSummon: () => void;
}

function getAgentDisplayName(config: AgentConfig | null): string | null {
  if (!config) {
    return null;
  }
  if (typeof config.agentName === 'string' && config.agentName.trim()) {
    return config.agentName.trim();
  }
  const legacyName = (config as AgentConfig & { name?: string }).name;
  if (typeof legacyName === 'string' && legacyName.trim()) {
    return legacyName.trim();
  }
  return null;
}

export function useFlowPadInlineRoute({ isOpen, mode, agentConfig, clearSummon }: UseFlowPadInlineRouteOptions) {
  const t = useTranslations('flowPad');
  const locale = useLocale();
  const agents = useAgentStore((state) => state.agents);
  const fetchAgents = useAgentStore((state) => state.fetchAgents);
  const fetchAgent = useAgentStore((state) => state.fetchAgent);
  const agentListLoading = useAgentStore((state) => state.loading);

  const [pickedRoute, setPickedRoute] = useState<InlineRouteSelection | null>(null);
  const [agentRouteMenuOpen, setAgentRouteMenuOpen] = useState(false);
  const [inlineRouteSwitching, setInlineRouteSwitching] = useState(false);
  const [inlineRouteSwitchError, setInlineRouteSwitchError] = useState<string | null>(null);
  const switchAbortRef = useRef<AbortController | null>(null);
  const agentRouteMenuRef = useRef<HTMLDivElement>(null);

  const availableAgents = useMemo(
    () =>
      agents.map((agent) => ({
        id: agent.id,
        name: getBuiltinAgentName(agent.id, agent.name, locale),
        avatar_url: agent.avatar_url,
      })),
    [agents, locale],
  );

  // An override whose agent has left the roster no longer applies: the pad falls back to the session route.
  const inlineRouteSelection = useMemo(
    () => (pickedRoute && availableAgents.some((agent) => agent.id === pickedRoute.id) ? pickedRoute : null),
    [pickedRoute, availableAgents],
  );

  const currentAgentLabel = useMemo(() => {
    const displayName = getAgentDisplayName(agentConfig);
    if (displayName === null) {
      return t('defaultAgent');
    }
    return agentConfig?.agentId ? getBuiltinAgentName(agentConfig.agentId, displayName, locale) : displayName;
  }, [agentConfig, locale, t]);
  const effectiveInlineRouteLabel = inlineRouteSelection?.name ?? currentAgentLabel;
  const effectiveInlineRouteAvatar = inlineRouteSelection?.avatarUrl ?? agentConfig?.avatarUrl;

  /** Drops the override and any in-flight switch; the pad calls it whenever a new session starts or ends. */
  const resetRoute = useCallback(() => {
    switchAbortRef.current?.abort();
    switchAbortRef.current = null;
    setPickedRoute(null);
    setInlineRouteSwitchError(null);
    setInlineRouteSwitching(false);
    setAgentRouteMenuOpen(false);
  }, []);

  useEffect(() => {
    if (!isOpen || mode !== 'inline') {
      return;
    }
    void fetchAgents(true);
  }, [isOpen, mode, fetchAgents]);

  useEffect(() => {
    if (!agentRouteMenuOpen) {
      return;
    }
    const onMouseDown = (event: MouseEvent) => {
      const target = event.target;
      if (target instanceof Node && !agentRouteMenuRef.current?.contains(target)) {
        setAgentRouteMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', onMouseDown);
    return () => document.removeEventListener('mousedown', onMouseDown);
  }, [agentRouteMenuOpen]);

  /** Resolves true once the route is applied; false when the switch failed or was superseded. */
  const selectRouteAgent = useCallback(
    async (agentId: string | null): Promise<boolean> => {
      setAgentRouteMenuOpen(false);
      clearSummon();
      if (agentId === null) {
        switchAbortRef.current?.abort();
        switchAbortRef.current = null;
        setPickedRoute(null);
        setInlineRouteSwitchError(null);
        setInlineRouteSwitching(false);
        return true;
      }
      if (inlineRouteSelection?.id === agentId) {
        return true;
      }

      switchAbortRef.current?.abort();
      const abortController = new AbortController();
      switchAbortRef.current = abortController;
      setInlineRouteSwitchError(null);
      setInlineRouteSwitching(true);
      try {
        const listItem = availableAgents.find((agent) => agent.id === agentId);
        const fullAgent = await fetchAgent(agentId, abortController.signal);
        if (abortController.signal.aborted) {
          return false;
        }
        if (!fullAgent) {
          throw new Error('Failed to load target agent profile');
        }
        const nextName = getBuiltinAgentName(agentId, listItem?.name ?? fullAgent.name, locale);
        setPickedRoute({
          id: agentId,
          name: nextName,
          avatarUrl: listItem?.avatar_url ?? fullAgent.avatar_url,
          config: buildAgentConfig(fullAgent),
        });
        setInlineRouteSwitchError(null);
        toast.success(t('inlineRouteApplied', { agent: nextName }), { duration: 2000 });
        return true;
      } catch (err) {
        if (abortController.signal.aborted) {
          return false;
        }
        console.error('FlowPad inline route switch failed:', err);
        const failedName = getBuiltinAgentName(
          agentId,
          availableAgents.find((agent) => agent.id === agentId)?.name ?? agentId,
          locale,
        );
        // Fail-safe to current session route to avoid accidentally sending with stale override.
        setPickedRoute(null);
        setInlineRouteSwitchError(failedName);
        toast.error(t('inlineRouteApplyFailed'), { duration: 3000 });
        return false;
      } finally {
        if (switchAbortRef.current === abortController) {
          switchAbortRef.current = null;
        }
        // An aborted switch was replaced by whoever aborted it, which owns the switching flag from here on.
        if (!abortController.signal.aborted) {
          setInlineRouteSwitching(false);
        }
      }
    },
    [availableAgents, fetchAgent, inlineRouteSelection?.id, locale, t, clearSummon],
  );

  const dismissRouteSwitchError = useCallback(() => setInlineRouteSwitchError(null), []);

  const fallbackToCurrentRoute = useCallback(() => {
    setPickedRoute(null);
    setInlineRouteSwitchError(null);
    clearSummon();
    toast.success(t('inlineRouteFallbackApplied'), { duration: 2000 });
  }, [t, clearSummon]);

  return {
    inlineRouteSelection,
    inlineRouteSwitching,
    inlineRouteSwitchError,
    agentRouteMenuOpen,
    setAgentRouteMenuOpen,
    agentRouteMenuRef,
    agentListLoading,
    availableAgents,
    currentAgentLabel,
    effectiveInlineRouteLabel,
    effectiveInlineRouteAvatar,
    selectRouteAgent,
    dismissRouteSwitchError,
    fallbackToCurrentRoute,
    resetRoute,
  };
}
