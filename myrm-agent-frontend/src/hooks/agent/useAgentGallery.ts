/**
 * 智能体画廊Hook
 *
 * 管理预置智能体和自定义智能体的状态、可用性检查、点击处理等逻辑
 *
 * @example
 * ```tsx
 * const {
 *   presetAgents,
 *   customAgents,
 *   handlePresetClick,
 *   handleCustomAgentClick,
 * } = useAgentGallery({
 *   onSelectPreset,
 *   onSelectCustomAgent,
 * });
 * ```
 */

import { isHiddenBuiltinAgent } from '@/lib/product-surface';
import { useMemo, useCallback, useEffect } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';
import type { PresetAgent } from '@/types/presetAgent';
import type { AgentListItem } from '@/services/agent';
import { AGENT_LIST_BUILTIN_PAGE_SIZE } from '@/services/agent';
import useAgentStore from '@/store/useAgentStore';
import useProviderStore from '@/store/useProviderStore';
import { isLocalMode } from '@/lib/deploy-mode';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import { toast } from '@/lib/utils/toast';

interface UseAgentGalleryParams {
  onSelectPreset: (agent: PresetAgent) => void;
  onSelectCustomAgent?: (agent: AgentListItem) => void;
}

export function useAgentGallery({ onSelectPreset, onSelectCustomAgent }: UseAgentGalleryParams) {
  const t = useTranslations('presetAgent');
  const locale = useLocale();

  // 获取 Provider 状态
  const { isInitialized, initProviders } = useProviderStore(
    useShallow((state) => ({
      isInitialized: state.isInitialized,
      initProviders: state.initProviders,
    })),
  );

  // 获取用户自定义智能体
  const { agents: customAgentsRaw, fetchAgents } = useAgentStore(
    useShallow((state) => ({
      agents: state.agents,
      fetchAgents: state.fetchAgents,
    })),
  );

  // 初始化
  useEffect(() => {
    if (!isInitialized) {
      initProviders();
    }
  }, [isInitialized, initProviders]);

  // 27 built-in presets exceed default page_size=20; fetch enough for gallery SSOT.
  // A forced fetch is not de-duplicated by the store, so it must not re-run when the providers finish starting.
  useEffect(() => {
    fetchAgents(1, AGENT_LIST_BUILTIN_PAGE_SIZE, true);
  }, [fetchAgents]);

  const isCLIVisualAgent = (agent: PresetAgent) => {
    return agent.category === 'cli_visual';
  };

  // 处理预置智能体的可用性
  // Sandbox 模式下过滤掉 CLI 可视化智能体（需要 Tauri Sidecar）
  const presetAgentsWithAvailability = useMemo(() => {
    const isLocal = isLocalMode();

    // 动态将后端 Built-in agents 映射为前端所需的 PresetAgent 格式
    const mappedPresets: PresetAgent[] = customAgentsRaw
      .filter((a) => a.is_built_in && !isHiddenBuiltinAgent(a.id))
      .map((bp) => {
        const isCli = bp.id === 'cli_visual' || bp.id === 'builtin-cli_visual';
        const category = isCli ? 'cli_visual' : 'general';

        return {
          id: bp.id,
          name: getBuiltinAgentName(bp.id, bp.name, locale),
          category,
          icon: bp.avatar_url?.replace('icon:', '') || 'MessageCircle',
          systemPrompt: '', // Only fetched when activated
          skillIds: [],
          isAvailable: true,
        };
      });

    return mappedPresets
      .filter((agent) => {
        // Sandbox 模式下：过滤掉 CLI 可视化类别的智能体
        if (!isLocal && agent.category === 'cli_visual') {
          return false;
        }
        return true;
      })
      .map((agent) => {
        if (isCLIVisualAgent(agent)) {
          // CLI 可视化智能体仅在本地模式下可用
          return { ...agent, isAvailable: isLocal };
        }
        return { ...agent, isAvailable: agent.isAvailable ?? true };
      });
  }, [customAgentsRaw, locale]);

  const customAgents = useMemo(() => customAgentsRaw.filter((a) => !a.is_built_in), [customAgentsRaw]);

  // 处理预置智能体点击（直接选中，无需展开）
  const handlePresetClick = useCallback(
    (agent: PresetAgent & { isAvailable?: boolean }) => {
      // CLI 可视化智能体在 Sandbox 模式下不可用
      if (isCLIVisualAgent(agent) && !agent.isAvailable) {
        toast.warning(t('notAvailable'), {
          description: t('tauriModeRequired'),
        });
        return;
      }

      onSelectPreset(agent);
    },
    [onSelectPreset, t],
  );

  // 处理自定义智能体点击
  const handleCustomAgentClick = useCallback(
    (agent: AgentListItem) => {
      onSelectCustomAgent?.(agent);
    },
    [onSelectCustomAgent],
  );

  return {
    presetAgents: presetAgentsWithAvailability,
    customAgents,
    handlePresetClick,
    handleCustomAgentClick,
  };
}
