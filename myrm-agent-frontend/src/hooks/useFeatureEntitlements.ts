'use client';

import { useEntitlements } from '@/hooks/useEntitlements';
import { isSandbox } from '@/lib/deploy-mode';

export function useFeatureEntitlements() {
  const sandbox = isSandbox();
  const { entitlements, isLoading } = useEntitlements();

  if (!sandbox) {
    return {
      isLoading: false,
      canUseCron: true,
      canUsePublicIngress: true,
      canUseSubagent: true,
      canUseVnc: true,
      plan: 'local' as const,
    };
  }

  return {
    isLoading,
    canUseCron: Boolean(entitlements?.enable_cron),
    canUsePublicIngress: Boolean(entitlements?.enable_public_ingress),
    canUseSubagent: Boolean(entitlements?.enable_subagent),
    canUseVnc: Boolean(entitlements?.enable_vnc),
    plan: entitlements?.plan ?? 'free',
  };
}
