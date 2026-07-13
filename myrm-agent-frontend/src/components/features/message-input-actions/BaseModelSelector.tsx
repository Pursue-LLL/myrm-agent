'use client';

import { useMemo, useCallback, useRef, useEffect } from 'react';
import { ChevronDown } from 'lucide-react';
import { useTranslations } from 'next-intl';
import useProviderStore from '@/store/useProviderStore';
import useChatStore from '@/store/useChatStore';
import { useShallow } from 'zustand/react/shallow';
import { resolveActiveModelSelection, resolveActiveFallbackSelection } from '@/lib/model-binding';
import { updateAgent, type AgentModelSelection } from '@/services/agent';
import ModelPickerPopover from '@/components/features/app-shell/model-picker-popover';
import ProviderIcon from '@/components/features/settings/model-service/ProviderIcon';
import { toast } from '@/hooks/useToast';
import type { AgentConfig } from '@/store/chat/types';

type SingleModelSelection = { providerId: string; model: string };

function buildFullModelSelection(config: AgentConfig): AgentModelSelection | null {
  if (!config.modelSelection) return null;
  return {
    providerId: config.modelSelection.providerId,
    model: config.modelSelection.model,
    fallbackProviderId: config.fallbackModelSelection?.providerId,
    fallbackModel: config.fallbackModelSelection?.model,
    safetyFallbackProviderId: config.safetyFallbackModelSelection?.providerId,
    safetyFallbackModel: config.safetyFallbackModelSelection?.model,
  };
}

const BaseModelSelector = () => {
  const commonT = useTranslations('common');

  const { agentConfig, actionMode, updateAgentConfig } = useChatStore(
    useShallow((state) => ({
      agentConfig: state.agentConfig,
      actionMode: state.actionMode,
      updateAgentConfig: state.updateAgentConfig,
    })),
  );

  const {
    providers,
    defaultModelConfig,
    getEnabledModels,
    setBaseModel,
    setBaseModelFallback,
    setFastModeModel,
    isInitialized,
    initProviders,
  } = useProviderStore(
    useShallow((state) => ({
      providers: state.providers,
      defaultModelConfig: state.defaultModelConfig,
      getEnabledModels: state.getEnabledModels,
      setBaseModel: state.setBaseModel,
      setBaseModelFallback: state.setBaseModelFallback,
      setFastModeModel: state.setFastModeModel,
      isInitialized: state.isInitialized,
      initProviders: state.initProviders,
    })),
  );

  useEffect(() => {
    if (!isInitialized) initProviders();
  }, [isInitialized, initProviders]);

  const enabledModels = useMemo(() => getEnabledModels(), [getEnabledModels, providers]);

  const currentSelection = useMemo(
    () => resolveActiveModelSelection(actionMode, agentConfig, defaultModelConfig, providers),
    [actionMode, agentConfig, defaultModelConfig, providers],
  );

  const fallbackSelection = useMemo(
    () => resolveActiveFallbackSelection(actionMode, agentConfig, defaultModelConfig, providers),
    [actionMode, agentConfig, defaultModelConfig, providers],
  );

  const safetyFallbackSelection = useMemo(
    () =>
      actionMode === 'agent' && agentConfig?.safetyFallbackModelSelection
        ? agentConfig.safetyFallbackModelSelection
        : null,
    [actionMode, agentConfig],
  );

  const isCurrentSelectionValid = useMemo(() => {
    if (!currentSelection) return false;
    return enabledModels.some(
      (m) => m.providerId === currentSelection.providerId && m.model === currentSelection.model,
    );
  }, [currentSelection, enabledModels]);

  const currentModelName = useMemo(
    () => (!currentSelection || !isCurrentSelectionValid ? commonT('notConfigured') : currentSelection.model),
    [currentSelection, isCurrentSelectionValid, commonT],
  );

  const syncTimerRef = useRef<NodeJS.Timeout | null>(null);
  useEffect(
    () => () => {
      if (syncTimerRef.current) clearTimeout(syncTimerRef.current);
    },
    [],
  );

  const syncAgentToBackend = useCallback(
    (configSnapshot: AgentConfig, rollback: () => void) => {
      if (!configSnapshot.agentId) return;
      const fullSelection = buildFullModelSelection(configSnapshot);
      if (!fullSelection) return;

      if (syncTimerRef.current) clearTimeout(syncTimerRef.current);
      syncTimerRef.current = setTimeout(() => {
        updateAgent(configSnapshot.agentId!, { model_selection: fullSelection }).catch(() => {
          rollback();
          toast({ title: commonT('modelSyncFailed'), variant: 'destructive' });
        });
      }, 500);
    },
    [commonT],
  );

  const handleModelSelect = useCallback(
    (providerId: string, model: string) => {
      const selection: SingleModelSelection = { providerId, model };

      if (actionMode === 'fast') {
        setFastModeModel(selection);
      } else if (actionMode === 'agent') {
        const prev = {
          modelSelection: agentConfig?.modelSelection ?? null,
          fallbackModelSelection: agentConfig?.fallbackModelSelection ?? null,
          safetyFallbackModelSelection: agentConfig?.safetyFallbackModelSelection ?? null,
        };
        updateAgentConfig({ modelSelection: selection });
        const snapshot: AgentConfig = {
          ...(agentConfig as AgentConfig),
          modelSelection: selection,
        };
        syncAgentToBackend(snapshot, () => updateAgentConfig(prev));
      } else {
        setBaseModel(selection);
      }
    },
    [actionMode, agentConfig, setFastModeModel, setBaseModel, updateAgentConfig, syncAgentToBackend],
  );

  const handleFallbackSelect = useCallback(
    (providerId: string, model: string) => {
      const selection: SingleModelSelection = { providerId, model };

      if (actionMode === 'agent') {
        const prevFallback = agentConfig?.fallbackModelSelection ?? null;
        updateAgentConfig({ fallbackModelSelection: selection });
        const snapshot: AgentConfig = {
          ...(agentConfig as AgentConfig),
          fallbackModelSelection: selection,
        };
        syncAgentToBackend(snapshot, () => updateAgentConfig({ fallbackModelSelection: prevFallback }));
      } else {
        setBaseModelFallback(selection);
      }
    },
    [actionMode, agentConfig, setBaseModelFallback, updateAgentConfig, syncAgentToBackend],
  );

  const handleClearFallback = useCallback(() => {
    if (actionMode === 'agent') {
      const prevFallback = agentConfig?.fallbackModelSelection ?? null;
      updateAgentConfig({ fallbackModelSelection: null });
      const snapshot: AgentConfig = {
        ...(agentConfig as AgentConfig),
        fallbackModelSelection: null,
      };
      syncAgentToBackend(snapshot, () => updateAgentConfig({ fallbackModelSelection: prevFallback }));
    } else {
      setBaseModelFallback(null);
    }
  }, [actionMode, agentConfig, setBaseModelFallback, updateAgentConfig, syncAgentToBackend]);

  const handleSafetyFallbackSelect = useCallback(
    (providerId: string, model: string) => {
      const selection: SingleModelSelection = { providerId, model };
      if (actionMode === 'agent') {
        const prevSafety = agentConfig?.safetyFallbackModelSelection ?? null;
        updateAgentConfig({ safetyFallbackModelSelection: selection });
        const snapshot: AgentConfig = {
          ...(agentConfig as AgentConfig),
          safetyFallbackModelSelection: selection,
        };
        syncAgentToBackend(snapshot, () => updateAgentConfig({ safetyFallbackModelSelection: prevSafety }));
      }
    },
    [actionMode, agentConfig, updateAgentConfig, syncAgentToBackend],
  );

  const handleClearSafetyFallback = useCallback(() => {
    if (actionMode === 'agent') {
      const prevSafety = agentConfig?.safetyFallbackModelSelection ?? null;
      updateAgentConfig({ safetyFallbackModelSelection: null });
      const snapshot: AgentConfig = {
        ...(agentConfig as AgentConfig),
        safetyFallbackModelSelection: null,
      };
      syncAgentToBackend(snapshot, () => updateAgentConfig({ safetyFallbackModelSelection: prevSafety }));
    }
  }, [actionMode, agentConfig, updateAgentConfig, syncAgentToBackend]);

  const isProviderDisabled = useMemo(() => {
    if (!currentSelection) return false;
    const provider = providers.find((p) => p.id === currentSelection.providerId);
    return provider ? !provider.isEnabled : true;
  }, [currentSelection, providers]);

  return (
    <div className="flex items-center gap-2">
      <ModelPickerPopover
        currentSelection={currentSelection}
        onSelect={handleModelSelect}
        fallbackSelection={fallbackSelection}
        onSelectFallback={handleFallbackSelect}
        onClearFallback={handleClearFallback}
        safetyFallbackSelection={safetyFallbackSelection}
        onSelectSafetyFallback={actionMode === 'agent' ? handleSafetyFallbackSelect : undefined}
        onClearSafetyFallback={actionMode === 'agent' ? handleClearSafetyFallback : undefined}
        trigger={
          <button
            type="button"
            data-testid="model-picker-trigger"
            className="group relative isolate flex h-fit focus:outline-none"
          >
            <div className="absolute inset-0 bg-black/[0.04] dark:bg-white/[0.06] rounded-[10px] transition-colors duration-300" />
            <div className="relative z-10 flex h-8 min-h-8 items-center gap-1.5 px-2.5 py-0.5">
              {currentSelection ? (
                <ProviderIcon
                  providerId={currentSelection.providerId}
                  size={16}
                  className="shrink-0 opacity-60 group-hover:opacity-100 transition-opacity duration-300"
                />
              ) : (
                <ChevronDown
                  size={16}
                  className="shrink-0 text-black/40 dark:text-white/40 group-hover:text-black dark:group-hover:text-white transition-colors duration-300"
                />
              )}
              <span className="inline text-xs font-medium text-black/60 dark:text-white/60 group-hover:text-black dark:group-hover:text-white transition-colors duration-300 truncate max-w-[160px] sm:max-w-none">
                {currentModelName}
              </span>
              <ChevronDown
                size={14}
                className="text-black/40 dark:text-white/40 group-hover:text-black dark:group-hover:text-white transition-colors duration-300"
              />
            </div>
          </button>
        }
      />
      {isProviderDisabled && (
        <span className="flex items-center text-amber-500" title={commonT('providerDisabledWarning')}>
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
            <path d="M12 9v4" />
            <path d="M12 17h.01" />
          </svg>
        </span>
      )}
    </div>
  );
};

export default BaseModelSelector;
