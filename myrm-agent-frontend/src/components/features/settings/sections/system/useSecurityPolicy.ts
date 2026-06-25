import { useState, useEffect, useCallback } from 'react';
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
import {
  flattenPermissions,
  buildPermissions,
  DEFAULT_CONFIG,
  createEmptyRule,
  DOMAIN_PATTERN,
} from './securityPolicyUtils';

const syncManager = getConfigSyncManager();

export function useSecurityPolicy(t: (key: string, fallback?: Record<string, string>) => string) {
  const [rules, setRules] = useState<PermissionRuleConfig[]>([]);
  const [timeout, setTimeout] = useState(DEFAULT_CONFIG.approvalTimeoutSeconds);
  const [timeoutBehavior, setTimeoutBehavior] = useState<'deny' | 'allow'>('deny');
  const [allowedRoots, setAllowedRoots] = useState<string[]>([]);
  const [networkAllowlist, setNetworkAllowlist] = useState<string[]>([]);
  const [domainHitlEnabled, setDomainHitlEnabled] = useState(true);
  const [yoloModeEnabled, setYoloModeEnabled] = useState(false);
  const [autoReviewEnabled, setAutoReviewEnabled] = useState(false);
  const [autoReviewModel, setAutoReviewModel] = useState<SingleModelSelection | null>(null);
  const [loaded, setLoaded] = useState(false);

  const { providers, getEnabledModels } = useProviderStore();
  const enabledModels = getEnabledModels();

  useEffect(() => {
    const cached = syncManager.get('securityConfig') as SecurityConfigValue | null;
    if (cached) {
      setRules(flattenPermissions(cached.permissions));
      setTimeout(cached.approvalTimeoutSeconds);
      setTimeoutBehavior(cached.approvalTimeoutBehavior ?? 'deny');
      setAllowedRoots(cached.pathPolicy?.allowedRoots ?? []);
      setNetworkAllowlist(cached.networkAllowlist ?? []);
      setDomainHitlEnabled(cached.domainHitlEnabled ?? false);
      setYoloModeEnabled(cached.yoloModeEnabled ?? false);
      setAutoReviewEnabled(cached.autoReviewEnabled ?? false);
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
      setRules(flattenPermissions(DEFAULT_CONFIG.permissions));
    }
    setLoaded(true);
  }, []);

  const save = useCallback(
    (
      overrides: {
        rules?: PermissionRuleConfig[];
        timeout?: number;
        pathPolicy?: PathPolicyConfig;
        behavior?: 'deny' | 'allow';
        domains?: string[];
        hitl?: boolean;
        yoloMode?: boolean;
        autoReview?: boolean;
        autoReviewModelStr?: string | null;
      } = {},
    ) => {
      const value: SecurityConfigValue = {
        permissions: buildPermissions(overrides.rules ?? rules),
        approvalTimeoutSeconds: overrides.timeout ?? timeout,
        approvalTimeoutBehavior: overrides.behavior ?? timeoutBehavior,
        pathPolicy:
          'pathPolicy' in overrides ? overrides.pathPolicy : allowedRoots.length > 0 ? { allowedRoots } : undefined,
        networkAllowlist: overrides.domains ?? networkAllowlist,
        domainHitlEnabled: overrides.hitl ?? domainHitlEnabled,
        yoloModeEnabled: overrides.yoloMode ?? yoloModeEnabled,
        autoReviewEnabled: overrides.autoReview ?? autoReviewEnabled,
        autoReviewModel:
          'autoReviewModelStr' in overrides
            ? overrides.autoReviewModelStr || undefined
            : autoReviewModel
              ? `${autoReviewModel.providerId}/${autoReviewModel.model}`
              : undefined,
      };
      syncManager.set('securityConfig', value);
    },
    [rules, timeout, timeoutBehavior, allowedRoots, networkAllowlist, domainHitlEnabled, yoloModeEnabled, autoReviewEnabled, autoReviewModel],
  );

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
      if (allowedRoots.includes(path)) return;
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

  const handleAddRule = useCallback(() => {
    setRules((prev) => [...prev, createEmptyRule()]);
  }, []);

  const handleRemoveRule = useCallback(
    (idx: number) => {
      setRules((prev) => {
        const next = prev.filter((_, i) => i !== idx);
        save({ rules: next });
        return next;
      });
      toast.success(t('ruleRemoved'));
    },
    [save, t],
  );

  const handleRuleChange = useCallback(
    (idx: number, field: keyof PermissionRuleConfig, value: string) => {
      setRules((prev) => {
        const next = prev.map((r, i) => (i === idx ? { ...r, [field]: value } : r));
        save({ rules: next });
        return next;
      });
    },
    [save],
  );

  const handleAddDomain = useCallback(
    (domain: string) => {
      const raw = domain
        .trim()
        .toLowerCase()
        .replace(/^https?:\/\//, '')
        .replace(/\/.*$/, '');
      if (!raw) return;
      if (!DOMAIN_PATTERN.test(raw)) {
        toast.error(t('domainAllowlist.invalidDomain'));
        return;
      }
      if (networkAllowlist.includes(raw)) {
        toast.error(t('domainAllowlist.duplicateDomain'));
        return;
      }
      const next = [...networkAllowlist, raw];
      setNetworkAllowlist(next);
      save({ domains: next });
      toast.success(t('domainAllowlist.domainAdded'));
    },
    [networkAllowlist, save, t],
  );

  const handleRemoveDomain = useCallback(
    (idx: number) => {
      const next = networkAllowlist.filter((_, i) => i !== idx);
      setNetworkAllowlist(next);
      save({ domains: next });
      toast.success(t('domainAllowlist.domainRemoved'));
    },
    [networkAllowlist, save, t],
  );

  const handleDomainHitlToggle = useCallback(
    (checked: boolean) => {
      setDomainHitlEnabled(checked);
      save({ hitl: checked });
      toast.success(t('domainAllowlist.saved'));
    },
    [save, t],
  );

  const handleYoloModeToggle = useCallback(
    (checked: boolean) => {
      setYoloModeEnabled(checked);
      save({ yoloMode: checked });
      toast.success(t('yoloMode.saved', { default: 'YOLO mode setting saved' }));
    },
    [save, t],
  );

  const handleAutoReviewToggle = useCallback(
    (checked: boolean) => {
      if (checked && !autoReviewModel && enabledModels.length > 0) {
        toast.error(
          t('autoReview.selectModelFirst', {
            default: 'Please select a reviewer model before enabling Smart Intent Guard.',
          }),
        );
        return;
      }
      setAutoReviewEnabled(checked);
      save({ autoReview: checked });
      toast.success(t('autoReview.saved', { default: 'Smart Intent Guard setting saved' }));
    },
    [save, t, autoReviewModel, enabledModels.length],
  );

  const handleAutoReviewModelChange = useCallback(
    (selection: SingleModelSelection | null) => {
      setAutoReviewModel(selection);
      if (!selection && autoReviewEnabled) {
        setAutoReviewEnabled(false);
        save({ autoReviewModelStr: null, autoReview: false });
        toast.success(t('autoReview.disabledNoModel', { default: 'Smart Intent Guard disabled — no model selected.' }));
        return;
      }
      save({ autoReviewModelStr: selection ? `${selection.providerId}/${selection.model}` : null });
      toast.success(t('autoReview.modelSaved', { default: 'Smart Intent Guard model saved' }));
    },
    [save, t, autoReviewEnabled],
  );

  const handleProfileSelect = useCallback(
    (profile: { config_json: Record<string, unknown> }) => {
      const cfg = profile.config_json;

      const perms = cfg.permissions as Record<string, PermissionAction | Record<string, PermissionAction>> | undefined;
      if (perms) {
        setRules(flattenPermissions(perms));
      }

      const pp = cfg.pathPolicy as { allowedRoots?: string[] } | undefined;
      const roots = pp?.allowedRoots ?? [];
      setAllowedRoots(roots);

      const cfgTimeout = cfg.approvalTimeoutSeconds as number | undefined;
      if (cfgTimeout !== undefined) setTimeout(cfgTimeout);

      const b = cfg.approvalTimeoutBehavior as 'deny' | 'allow' | undefined;
      if (b) setTimeoutBehavior(b);

      const na = cfg.networkAllowlist as string[] | undefined;
      if (na) setNetworkAllowlist(na);

      const dh = cfg.domainHitlEnabled as boolean | undefined;
      if (dh !== undefined) setDomainHitlEnabled(dh);

      const ym = cfg.yoloModeEnabled as boolean | undefined;
      if (ym !== undefined) setYoloModeEnabled(ym);

      const ar = cfg.autoReviewEnabled as boolean | undefined;
      if (ar !== undefined) setAutoReviewEnabled(ar);

      save({
        rules: perms ? flattenPermissions(perms) : undefined,
        pathPolicy: roots.length > 0 ? { allowedRoots: roots } : undefined,
        timeout: cfgTimeout,
        behavior: b,
        domains: na,
        hitl: dh,
        yoloMode: ym,
        autoReview: ar,
      });

      toast.success('Profile loaded');
    },
    [save],
  );

  const handleNLApply = useCallback(
    (generated: Record<string, unknown>) => {
      const perms = generated.permissions as
        | Record<string, PermissionAction | Record<string, PermissionAction>>
        | undefined;
      const newRules = perms ? flattenPermissions(perms) : undefined;

      const pp = generated.pathPolicy as { allowedRoots?: string[] } | undefined;
      const newRoots = pp?.allowedRoots ?? undefined;

      const na = generated.networkAllowlist as string[] | undefined;
      const hitl = generated.domainHitlEnabled;

      if (newRules) setRules(newRules);
      if (newRoots) setAllowedRoots(newRoots);
      if (na) setNetworkAllowlist(na);
      if (hitl !== undefined) setDomainHitlEnabled(Boolean(hitl));

      save({
        rules: newRules,
        pathPolicy: newRoots ? { allowedRoots: newRoots } : undefined,
        domains: na,
        hitl: hitl !== undefined ? Boolean(hitl) : undefined,
      });
    },
    [save],
  );

  return {
    rules,
    timeout,
    timeoutBehavior,
    allowedRoots,
    networkAllowlist,
    domainHitlEnabled,
    yoloModeEnabled,
    autoReviewEnabled,
    autoReviewModel,
    loaded,
    providers,
    enabledModels,
    handleAddRoot,
    handleRemoveRoot,
    handleTimeoutChange,
    handleTimeoutBehaviorChange,
    handleAddRule,
    handleRemoveRule,
    handleRuleChange,
    handleAddDomain,
    handleRemoveDomain,
    handleDomainHitlToggle,
    handleYoloModeToggle,
    handleAutoReviewToggle,
    handleAutoReviewModelChange,
    handleProfileSelect,
    handleNLApply,
  };
}
