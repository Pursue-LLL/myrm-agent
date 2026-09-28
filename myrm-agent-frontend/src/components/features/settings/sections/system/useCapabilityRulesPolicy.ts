import { useState, useCallback } from 'react';
import { toast } from '@/lib/utils/toast';
import type { PermissionAction, PermissionRuleConfig } from '@/services/config/types';
import {
  createEmptyRule,
  syncCapabilityActionToRules,
  deriveCapabilityMatrix,
  type CapabilitySurfaceKey,
  type CapabilityMatrix,
} from './securityPolicyUtils';

export interface UseCapabilityRulesPolicyOptions {
  onSave: (overrides: { rules?: PermissionRuleConfig[]; capabilityMatrix?: Record<string, PermissionAction> }) => void;
  t: (key: string, fallback?: Record<string, string>) => string;
}

export function useCapabilityRulesPolicy({ onSave, t }: UseCapabilityRulesPolicyOptions) {
  const [rules, setRules] = useState<PermissionRuleConfig[]>([]);
  const [capabilityMatrix, setCapabilityMatrix] = useState<CapabilityMatrix>(() => deriveCapabilityMatrix());

  const handleAddRule = useCallback(() => {
    setRules((prev) => [...prev, createEmptyRule()]);
  }, []);

  const handleRemoveRule = useCallback(
    (idx: number) => {
      setRules((prev) => {
        const next = prev.filter((_, i) => i !== idx);
        onSave({ rules: next });
        return next;
      });
      toast.success(t('ruleRemoved'));
    },
    [onSave, t],
  );

  const handleRuleChange = useCallback(
    (idx: number, field: keyof PermissionRuleConfig, value: string) => {
      setRules((prev) => {
        const next = prev.map((r, i) => (i === idx ? { ...r, [field]: value } : r));
        onSave({ rules: next });
        return next;
      });
    },
    [onSave],
  );

  const handleCapabilityChange = useCallback(
    (surfaceKey: CapabilitySurfaceKey, action: PermissionAction) => {
      const nextMatrix: CapabilityMatrix = {
        ...capabilityMatrix,
        [surfaceKey]: action,
      };
      setCapabilityMatrix(nextMatrix);
      const nextRules = syncCapabilityActionToRules(rules, surfaceKey, action);
      setRules(nextRules);
      onSave({
        capabilityMatrix: nextMatrix,
        rules: nextRules,
      });
      toast.success(t('capabilitySurfaceSaved', { default: 'Capability surface permission updated' }));
    },
    [capabilityMatrix, onSave, rules, t],
  );

  const handleCapabilityPresetApply = useCallback(
    (presetMatrix: CapabilityMatrix) => {
      setCapabilityMatrix(presetMatrix);
      let nextRules = [...rules];
      for (const [key, action] of Object.entries(presetMatrix)) {
        nextRules = syncCapabilityActionToRules(nextRules, key as CapabilitySurfaceKey, action);
      }
      setRules(nextRules);
      onSave({
        capabilityMatrix: presetMatrix,
        rules: nextRules,
      });
      toast.success(t('capabilityPresetApplied', { default: 'Security posture preset applied' }));
    },
    [onSave, rules, t],
  );

  return {
    rules,
    setRules,
    capabilityMatrix,
    setCapabilityMatrix,
    handleAddRule,
    handleRemoveRule,
    handleRuleChange,
    handleCapabilityChange,
    handleCapabilityPresetApply,
  };
}
