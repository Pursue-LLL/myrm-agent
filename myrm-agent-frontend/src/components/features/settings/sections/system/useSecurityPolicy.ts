import { useState, useEffect, useCallback, useRef } from 'react';
import { toast } from '@/lib/utils/toast';
import { getConfigSyncManager } from '@/services/config';
import useProviderStore from '@/store/useProviderStore';
import type { SingleModelSelection } from '@/store/config/providerTypes';
import type {
  PermissionAction,
  PermissionRuleConfig,
  SecurityConfigValue,
  PathPolicyConfig,
} from '@/services/config/types';
import { flattenPermissions, buildPermissions, DEFAULT_CONFIG, deriveCapabilityMatrix } from './securityPolicyUtils';
import { useManagedPolicyEffective } from '@/hooks/useManagedPolicyEffective';
import { useCapabilityRulesPolicy } from './useCapabilityRulesPolicy';
import { useNetworkCommandPolicy } from './useNetworkCommandPolicy';
import { parseProfileConfig, parseNLGeneratedConfig } from './securityProfileUtils';

const syncManager = getConfigSyncManager();

export interface SecuritySaveOverrides {
  rules?: PermissionRuleConfig[];
  capabilityMatrix?: Record<string, PermissionAction>;
  timeout?: number;
  pathPolicy?: PathPolicyConfig;
  behavior?: 'deny' | 'allow';
  domains?: string[];
  blockedDomains?: string[];
  cmdDenylist?: string[];
  hitl?: boolean;
  injection?: 'log_only' | 'fail_closed';
  planConfirm?: boolean;
  yoloMode?: boolean;
  autoReview?: boolean;
  autoReviewModelStr?: string | null;
}

export function useSecurityPolicy(t: (key: string, fallback?: Record<string, string>) => string) {
  const [timeout, setTimeout] = useState(DEFAULT_CONFIG.approvalTimeoutSeconds);
  const [timeoutBehavior, setTimeoutBehavior] = useState<'deny' | 'allow'>('deny');
  const [allowedRoots, setAllowedRoots] = useState<string[]>([]);
  const [injectionPolicy, setInjectionPolicy] = useState<'log_only' | 'fail_closed'>('log_only');
  const [planConfirmEnabled, setPlanConfirmEnabled] = useState(false);
  const [yoloModeEnabled, setYoloModeEnabled] = useState(false);
  const [autoReviewEnabled, setAutoReviewEnabled] = useState(true);
  const [autoReviewModel, setAutoReviewModel] = useState<SingleModelSelection | null>(null);
  const [loaded, setLoaded] = useState(false);

  const {
    policy: managedPolicyEffective,
    active: managedPolicyActive,
    loaded: managedPolicyLoaded,
  } = useManagedPolicyEffective();
  const managedDisableYolo = Boolean(managedPolicyEffective.disableYolo);
  const managedDisableAllowAlways = Boolean(managedPolicyEffective.disableAllowAlways);

  const { providers, getEnabledModels } = useProviderStore();
  const enabledModels = getEnabledModels();

  const stateRef = useRef({
    rules: [] as PermissionRuleConfig[],
    capabilityMatrix: {} as Record<string, PermissionAction>,
    timeout,
    timeoutBehavior,
    allowedRoots,
    networkAllowlist: [] as string[],
    networkBlocklist: [] as string[],
    commandDenylist: [] as string[],
    domainHitlEnabled: true,
    injectionPolicy,
    planConfirmEnabled,
    yoloModeEnabled,
    autoReviewEnabled,
    autoReviewModel,
  });

  const save = useCallback((overrides: SecuritySaveOverrides = {}) => {
    const s = stateRef.current;
    const value: SecurityConfigValue = {
      permissions: buildPermissions(overrides.rules ?? s.rules),
      capabilityMatrix: overrides.capabilityMatrix ?? s.capabilityMatrix,
      approvalTimeoutSeconds: overrides.timeout ?? s.timeout,
      approvalTimeoutBehavior: overrides.behavior ?? s.timeoutBehavior,
      pathPolicy:
        'pathPolicy' in overrides
          ? overrides.pathPolicy
          : s.allowedRoots.length > 0
            ? { allowedRoots: s.allowedRoots }
            : undefined,
      networkAllowlist: overrides.domains ?? s.networkAllowlist,
      networkBlocklist: overrides.blockedDomains ?? s.networkBlocklist,
      commandDenylist: overrides.cmdDenylist ?? s.commandDenylist,
      domainHitlEnabled: overrides.hitl ?? s.domainHitlEnabled,
      injectionPolicy: overrides.injection ?? s.injectionPolicy,
      planConfirmEnabled: overrides.planConfirm ?? s.planConfirmEnabled,
      yoloModeEnabled: overrides.yoloMode ?? s.yoloModeEnabled,
      autoReviewEnabled: overrides.autoReview ?? s.autoReviewEnabled,
      autoReviewModel:
        'autoReviewModelStr' in overrides
          ? overrides.autoReviewModelStr || undefined
          : s.autoReviewModel
            ? `${s.autoReviewModel.providerId}/${s.autoReviewModel.model}`
            : undefined,
    };
    syncManager.set('securityConfig', value);
  }, []);

  const capabilityRules = useCapabilityRulesPolicy({ onSave: save, t });
  const networkCommand = useNetworkCommandPolicy({ onSave: save, t });

  stateRef.current = {
    rules: capabilityRules.rules,
    capabilityMatrix: capabilityRules.capabilityMatrix,
    timeout,
    timeoutBehavior,
    allowedRoots,
    networkAllowlist: networkCommand.networkAllowlist,
    networkBlocklist: networkCommand.networkBlocklist,
    commandDenylist: networkCommand.commandDenylist,
    domainHitlEnabled: networkCommand.domainHitlEnabled,
    injectionPolicy,
    planConfirmEnabled,
    yoloModeEnabled,
    autoReviewEnabled,
    autoReviewModel,
  };

  useEffect(() => {
    const cached = syncManager.get('securityConfig') as SecurityConfigValue | null;
    if (cached) {
      const flattened = flattenPermissions(cached.permissions ?? DEFAULT_CONFIG.permissions);
      capabilityRules.setRules(flattened);
      capabilityRules.setCapabilityMatrix(deriveCapabilityMatrix(cached.capabilityMatrix, flattened));
      setTimeout(cached.approvalTimeoutSeconds);
      setTimeoutBehavior(cached.approvalTimeoutBehavior ?? 'deny');
      setAllowedRoots(cached.pathPolicy?.allowedRoots ?? []);
      networkCommand.setNetworkAllowlist(cached.networkAllowlist ?? []);
      networkCommand.setNetworkBlocklist(cached.networkBlocklist ?? []);
      networkCommand.setCommandDenylist(cached.commandDenylist ?? []);
      networkCommand.setDomainHitlEnabled(cached.domainHitlEnabled ?? false);
      setInjectionPolicy(cached.injectionPolicy ?? 'log_only');
      setPlanConfirmEnabled(cached.planConfirmEnabled ?? false);
      setYoloModeEnabled(cached.yoloModeEnabled ?? false);
      setAutoReviewEnabled(cached.autoReviewEnabled ?? true);
      if (cached.autoReviewModel) {
        const parts = cached.autoReviewModel.split('/');
        if (parts.length === 2) {
          setAutoReviewModel({ providerId: parts[0], model: parts[1] });
        } else {
          const found = enabledModels.find((m) => m.model === cached.autoReviewModel);
          if (found) {
            setAutoReviewModel({ providerId: found.providerId, model: found.model });
          }
        }
      }
    } else {
      const defaultRules = flattenPermissions(DEFAULT_CONFIG.permissions);
      capabilityRules.setRules(defaultRules);
      capabilityRules.setCapabilityMatrix(deriveCapabilityMatrix(undefined, defaultRules));
    }
    setLoaded(true);
  }, []);

  useEffect(() => {
    const syncYoloFromConfig = () => {
      const config = syncManager.get('securityConfig');
      setYoloModeEnabled(config?.yoloModeEnabled ?? false);
    };
    syncYoloFromConfig();
    return syncManager.subscribe('securityConfig', syncYoloFromConfig);
  }, []);

  const savePathPolicy = useCallback(
    (roots: string[]) => {
      const pp: PathPolicyConfig | undefined = roots.length > 0 ? { allowedRoots: roots } : undefined;
      save({ pathPolicy: pp });
      toast.success(t('pathPolicySaved'));
    },
    [save, t],
  );

  const handleAddRoot = useCallback(
    (path: string) => {
      if (allowedRoots.includes(path)) {
        return;
      }
      const next = [...allowedRoots, path];
      setAllowedRoots(next);
      savePathPolicy(next);
    },
    [allowedRoots, savePathPolicy],
  );

  const handleRemoveRoot = useCallback(
    (idx: number) => {
      const next = allowedRoots.filter((_, i) => i !== idx);
      setAllowedRoots(next);
      savePathPolicy(next);
    },
    [allowedRoots, savePathPolicy],
  );

  const handleTimeoutChange = useCallback(
    (val: string) => {
      const n = Math.max(10, Math.min(600, Number(val) || 120));
      setTimeout(n);
      save({ timeout: n });
    },
    [save],
  );

  const handleTimeoutBehaviorChange = useCallback(
    (val: 'deny' | 'allow') => {
      setTimeoutBehavior(val);
      save({ behavior: val });
    },
    [save],
  );

  const handleInjectionPolicyToggle = useCallback(
    (checked: boolean) => {
      const next = checked ? 'fail_closed' : 'log_only';
      setInjectionPolicy(next);
      save({ injection: next });
      toast.success(t('injectionPolicy.saved', { default: 'Prompt injection policy saved' }));
    },
    [save, t],
  );

  const handlePlanConfirmToggle = useCallback(
    (checked: boolean) => {
      setPlanConfirmEnabled(checked);
      save({ planConfirm: checked });
      toast.success(t('planReview.saved', { default: 'Plan review setting saved' }));
    },
    [save, t],
  );

  const handleYoloModeToggle = useCallback(
    (checked: boolean) => {
      if (checked && managedDisableYolo) {
        toast.error(
          t('managedPolicy.yoloLocked', {
            default: 'YOLO mode is disabled by your organization policy.',
          }),
        );
        return;
      }
      setYoloModeEnabled(checked);
      if (checked && planConfirmEnabled) {
        setPlanConfirmEnabled(false);
        save({ yoloMode: checked, planConfirm: false });
      } else {
        save({ yoloMode: checked });
      }
      toast.success(t('yoloMode.saved', { default: 'YOLO mode setting saved' }));
    },
    [save, t, planConfirmEnabled, managedDisableYolo],
  );

  const handleAutoReviewToggle = useCallback(
    (checked: boolean) => {
      setAutoReviewEnabled(checked);
      save({ autoReview: checked });
      toast.success(t('autoReview.saved', { default: 'Smart Intent Guard setting saved' }));
    },
    [save, t],
  );

  const handleAutoReviewModelChange = useCallback(
    (selection: SingleModelSelection | null) => {
      setAutoReviewModel(selection);
      save({ autoReviewModelStr: selection ? `${selection.providerId}/${selection.model}` : null });
      toast.success(
        selection
          ? t('autoReview.modelSaved', { default: 'Smart Intent Guard model saved' })
          : t('autoReview.modelCleared', { default: 'Reviewer model cleared — using default model as fallback.' }),
      );
    },
    [save, t],
  );

  const handleProfileSelect = useCallback(
    (profile: { config_json: Record<string, unknown> }) => {
      const parsed = parseProfileConfig(profile.config_json);

      if (parsed.rules && parsed.derivedMatrix) {
        capabilityRules.setRules(parsed.rules);
        capabilityRules.setCapabilityMatrix(parsed.derivedMatrix);
      }
      setAllowedRoots(parsed.roots);
      if (parsed.timeout !== undefined) setTimeout(parsed.timeout);
      if (parsed.behavior) setTimeoutBehavior(parsed.behavior);
      if (parsed.domains) networkCommand.setNetworkAllowlist(parsed.domains);
      if (parsed.blockedDomains) networkCommand.setNetworkBlocklist(parsed.blockedDomains);
      if (parsed.cmdDenylist) networkCommand.setCommandDenylist(parsed.cmdDenylist);
      if (parsed.hitl !== undefined) networkCommand.setDomainHitlEnabled(parsed.hitl);
      if (parsed.injection !== undefined) setInjectionPolicy(parsed.injection);
      if (parsed.planConfirm !== undefined) setPlanConfirmEnabled(parsed.planConfirm);
      if (parsed.yoloMode !== undefined) setYoloModeEnabled(parsed.yoloMode);
      if (parsed.autoReview !== undefined) setAutoReviewEnabled(parsed.autoReview);

      save({
        rules: parsed.rules,
        capabilityMatrix: parsed.capabilityMatrix,
        pathPolicy: parsed.roots.length > 0 ? { allowedRoots: parsed.roots } : undefined,
        timeout: parsed.timeout,
        behavior: parsed.behavior,
        domains: parsed.domains,
        blockedDomains: parsed.blockedDomains,
        cmdDenylist: parsed.cmdDenylist,
        hitl: parsed.hitl,
        injection: parsed.injection,
        planConfirm: parsed.planConfirm,
        yoloMode: parsed.yoloMode,
        autoReview: parsed.autoReview,
      });

      toast.success('Profile loaded');
    },
    [capabilityRules, networkCommand, save],
  );

  const handleNLApply = useCallback(
    (generated: Record<string, unknown>) => {
      const parsed = parseNLGeneratedConfig(generated);

      if (parsed.rules) capabilityRules.setRules(parsed.rules);
      if (parsed.roots) setAllowedRoots(parsed.roots);
      if (parsed.domains) networkCommand.setNetworkAllowlist(parsed.domains);
      if (parsed.blockedDomains) networkCommand.setNetworkBlocklist(parsed.blockedDomains);
      if (parsed.cmdDenylist) networkCommand.setCommandDenylist(parsed.cmdDenylist);
      if (parsed.hitl !== undefined) networkCommand.setDomainHitlEnabled(parsed.hitl);
      if (parsed.planConfirm !== undefined) setPlanConfirmEnabled(parsed.planConfirm);

      save({
        rules: parsed.rules,
        pathPolicy: parsed.roots ? { allowedRoots: parsed.roots } : undefined,
        domains: parsed.domains,
        blockedDomains: parsed.blockedDomains,
        cmdDenylist: parsed.cmdDenylist,
        hitl: parsed.hitl,
        planConfirm: parsed.planConfirm,
      });
    },
    [capabilityRules, networkCommand, save],
  );

  return {
    rules: capabilityRules.rules,
    timeout,
    timeoutBehavior,
    allowedRoots,
    networkAllowlist: networkCommand.networkAllowlist,
    networkBlocklist: networkCommand.networkBlocklist,
    commandDenylist: networkCommand.commandDenylist,
    domainHitlEnabled: networkCommand.domainHitlEnabled,
    injectionPolicy,
    planConfirmEnabled,
    yoloModeEnabled,
    autoReviewEnabled,
    autoReviewModel,
    loaded,
    managedPolicyLoaded,
    managedPolicyActive,
    managedDisableYolo,
    managedDisableAllowAlways,
    managedPolicyEffective,
    providers,
    enabledModels,
    handleAddRoot,
    handleRemoveRoot,
    handleTimeoutChange,
    handleTimeoutBehaviorChange,
    handleAddRule: capabilityRules.handleAddRule,
    handleRemoveRule: capabilityRules.handleRemoveRule,
    handleRuleChange: capabilityRules.handleRuleChange,
    handleAddDomain: networkCommand.handleAddDomain,
    handleRemoveDomain: networkCommand.handleRemoveDomain,
    handleAddBlockedDomain: networkCommand.handleAddBlockedDomain,
    handleRemoveBlockedDomain: networkCommand.handleRemoveBlockedDomain,
    handleAddCommandPattern: networkCommand.handleAddCommandPattern,
    handleRemoveCommandPattern: networkCommand.handleRemoveCommandPattern,
    handleDomainHitlToggle: networkCommand.handleDomainHitlToggle,
    handleInjectionPolicyToggle,
    handlePlanConfirmToggle,
    handleYoloModeToggle,
    handleAutoReviewToggle,
    handleAutoReviewModelChange,
    handleProfileSelect,
    handleNLApply,
    capabilityMatrix: capabilityRules.capabilityMatrix,
    handleCapabilityChange: capabilityRules.handleCapabilityChange,
    handleCapabilityPresetApply: capabilityRules.handleCapabilityPresetApply,
  };
}
