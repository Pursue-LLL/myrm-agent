'use client';

import { useCallback } from 'react';
import { useShallow } from 'zustand/react/shallow';
import useConfigStore from '@/store/useConfigStore';
import { getConfigSyncManager } from '@/services/config';
import { DEFAULT_PERSONAL_SETTINGS, type PersonalSettingsConfigValue } from '@/services/config/types';

function selectPersonalSettings(state: ReturnType<typeof useConfigStore.getState>): PersonalSettingsConfigValue {
  return {
    ...DEFAULT_PERSONAL_SETTINGS,
    ...state.personalSettings,
    systemInstructions: state.systemInstructions,
    fetchRawWebpage: state.fetchRawWebpage,
    generateSearchSuggestions: state.generateSearchSuggestions,
    enableCostEstimation: state.enableCostEstimation,
    enableCacheBreakNotification: state.enableCacheBreakNotification,
    showContextUsage: state.showContextUsage,
    enableMemory: state.enableMemory,
    memoryRequireConfirmation: state.memoryRequireConfirmation,
    enableMemoryAutoExtraction: state.enableMemoryAutoExtraction,
    preCompactEnabled: state.preCompactEnabled,
    preCompactBudgetTokens: state.preCompactBudgetTokens,
    enableAutoTitleGeneration: state.enableAutoTitleGeneration,
    webTtsProvider: state.webTtsProvider,
    timezone: state.timezone,
    locale: state.personalSettings?.locale,
    customPrimaryColor: state.customPrimaryColor,
    enableWebNotifications: state.enableWebNotifications,
    enableCompletionSound: state.enableCompletionSound,
    notificationDeliveries: state.personalSettings?.notificationDeliveries,
    privacyEnabled: state.privacyEnabled,
    privacyS2Action: state.privacyS2Action,
    privacyS3Action: state.privacyS3Action,
    codeExecutionAllowNetwork: state.codeExecutionAllowNetwork,
    enableEvalLab: state.enableEvalLab,
    smoothStreamEnabled: state.smoothStreamEnabled,
    publicIngressBaseUrl: state.publicIngressBaseUrl,
  };
}

export function usePersonalSettings() {
  const syncManager = getConfigSyncManager();
  const personalSettings = useConfigStore(useShallow(selectPersonalSettings));

  const updatePersonalSettings = useCallback(
    (patch: Partial<PersonalSettingsConfigValue>) => {
      const current = syncManager.get('personalSettings') ?? DEFAULT_PERSONAL_SETTINGS;
      const merged: PersonalSettingsConfigValue = { ...current, ...patch };
      syncManager.set('personalSettings', merged);
      useConfigStore.setState({
        ...patch,
        personalSettings: merged,
      });
    },
    [syncManager],
  );

  return { personalSettings, updatePersonalSettings };
}
