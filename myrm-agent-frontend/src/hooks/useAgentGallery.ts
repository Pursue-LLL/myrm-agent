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
 *   workingDirectory,
 *   handleWorkingDirectoryChange,
 *   cliCardRef
 * } = useAgentGallery({
 *   onSelectPreset,
 *   onSelectCustomAgent,
 *   externalWorkingDirectory
 * });
 * ```
 */

import { useMemo, useCallback, useEffect, useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations, useLocale } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';
import type { PresetAgent } from '@/types/presetAgent';
import type { AgentListItem } from '@/services/agent';
import useAgentStore from '@/store/useAgentStore';
import useProviderStore from '@/store/useProviderStore';
import { isLocalMode } from '@/lib/deploy-mode';
import { toast } from '@/lib/utils/toast';
import { isAbsolutePath, normalizePath } from '@/utils/pathValidation';
import { CLI_WORKING_DIRECTORY_STORAGE_KEY } from '@/components/ui/chat-window/agent-config-panel/constants';

interface UseAgentGalleryParams {
  onSelectPreset: (agent: PresetAgent, workingDirectory?: string) => void;
  onSelectCustomAgent?: (agent: AgentListItem) => void;
  externalWorkingDirectory?: string;
}

export function useAgentGallery({
  onSelectPreset,
  onSelectCustomAgent,
  externalWorkingDirectory,
}: UseAgentGalleryParams) {
  const t = useTranslations('presetAgent');
  const locale = useLocale();
  const router = useRouter();

  // 本地管理的工作目录状态（从 localStorage 读取）
  const [localWorkingDirectory, setLocalWorkingDirectory] = useState<string>(() => {
    if (typeof window === 'undefined') return '';
    return localStorage.getItem(CLI_WORKING_DIRECTORY_STORAGE_KEY) || '';
  });

  // 使用本地状态或外部传入的工作目录
  const effectiveWorkingDirectory = localWorkingDirectory || externalWorkingDirectory;

  // 保存工作目录到 localStorage
  const handleWorkingDirectoryChange = useCallback((directory: string) => {
    setLocalWorkingDirectory(directory);
    localStorage.setItem(CLI_WORKING_DIRECTORY_STORAGE_KEY, directory);
  }, []);

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
    fetchAgents();
  }, [isInitialized, initProviders, fetchAgents]);

  const isCLIVisualAgent = (agent: PresetAgent) => {
    return agent.category === 'cli_visual' && agent.requiresWorkingDirectory === true;
  };

  // 处理预置智能体的可用性
  // Sandbox 模式下过滤掉 CLI 可视化智能体（需要 Tauri Sidecar）
  const presetAgentsWithAvailability = useMemo(() => {
    const isLocal = isLocalMode();

    // 动态将后端 Built-in agents 映射为前端所需的 PresetAgent 格式
    const mappedPresets: PresetAgent[] = customAgentsRaw
      .filter((a) => a.is_built_in)
      .map((bp) => {
        const isCli = bp.id === 'cli_visual' || bp.id === 'builtin-cli_visual';
        const category = isCli ? 'cli_visual' : 'general';

        return {
          id: bp.id,
          name: bp.name,
          nameKey: bp.id.replace('builtin-', ''), // Map ID to translation key
          description: bp.description || '',
          descriptionKey: bp.id.replace('builtin-', ''),
          category: category as any,
          icon: bp.avatar_url?.replace('icon:', '') || 'MessageCircle',
          systemPrompt: '', // Only fetched when activated
          skillIds: [],
          tools: [],
          requiresWorkingDirectory: isCli,
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

  // 用于震动动画的 ref
  const cliCardRef = useRef<HTMLDivElement>(null);

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

      // CLI 智能体需要有效的绝对工作路径
      if (isCLIVisualAgent(agent) && agent.requiresWorkingDirectory) {
        // 规范化路径：去除末尾斜杠
        const normalizedPath = normalizePath(effectiveWorkingDirectory || '');

        // 检查是否填写或是否为绝对路径
        if (!normalizedPath || !isAbsolutePath(normalizedPath)) {
          // 仅震动提示，不显示 toast
          if (cliCardRef.current) {
            cliCardRef.current.classList.add('animate-shake');
            setTimeout(() => {
              cliCardRef.current?.classList.remove('animate-shake');
            }, 500);
          }
          return;
        }

        // 有效的绝对路径，传递给回调（已规范化）
        onSelectPreset(agent, normalizedPath);
        return;
      }

      onSelectPreset(agent);
    },
    [onSelectPreset, t, router, effectiveWorkingDirectory],
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
    workingDirectory: effectiveWorkingDirectory,
    handleWorkingDirectoryChange,
    cliCardRef,
  };
}
