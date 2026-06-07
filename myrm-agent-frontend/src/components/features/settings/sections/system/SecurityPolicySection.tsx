'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconPlus,
  IconTrash,
  IconShieldCheck,
  IconShieldAlert,
  IconBan,
  IconEye,
  IconEyeOff,
  IconShield,
  IconLoader,
  IconZap,
  IconAlertTriangle,
  IconRefresh,
  IconSearch,
} from '@/components/features/icons/PremiumIcons';
import { Navigation } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { fetchWithTimeout } from '@/lib/api';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Switch } from '@/components/primitives/switch';
import { toast } from '@/lib/utils/toast';
import { getConfigSyncManager } from '@/services/config';
import useConfigStore from '@/store/useConfigStore';
import useProviderStore from '@/store/useProviderStore';
import EnabledModelSelect from '../../default-model/EnabledModelSelect';
import type { SingleModelSelection } from '@/store/config/providerTypes';
import type {
  PermissionAction,
  PermissionRuleConfig,
  SecurityConfigValue,
  PathPolicyConfig,
  PIIAction,
  PrivacyRoutingConfig,
  PrivacyS2Strategy,
  PrivacyS3Strategy,
  PrivacyLocalFallback,
} from '@/services/config/types';
import SettingsSection from '../SettingsSection';
import { PathPolicyEditor } from './PathPolicyEditor';
import { DomainAllowlistEditor } from './DomainAllowlistEditor';
import AllowlistSection from './AllowlistSection';
import { AdvancedPiiConfig } from './AdvancedPiiConfig';
import NLPolicyGenerator from './NLPolicyGenerator';
import SecurityProfileSelector from './SecurityProfileSelector';

const DOMAIN_PATTERN =
  /^(\*\.)?([a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?\.)*[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(:\d{1,5})?$/;

const BUILTIN_BLACKLIST = ['rm -rf /', 'rm -rf /*', 'mkfs*', 'dd if=*', 'chmod 777 /*', ':(){ :|:& };:'];

const KNOWN_PERMISSIONS = [
  'web_search_tool',
  'net_fetch',
  'shell_exec',
  'file_read',
  'file_write',
  'mcp_invoke',
  'code_interpreter_tool',
  'browser_navigate',
  'browser_fill',
  'browser_upload',
  'browser_download',
  'browser_session',
] as const;

function flattenPermissions(
  perms: Record<string, PermissionAction | Record<string, PermissionAction>>,
): PermissionRuleConfig[] {
  const rules: PermissionRuleConfig[] = [];
  for (const [key, value] of Object.entries(perms)) {
    if (typeof value === 'string') {
      rules.push({ permission: key, pattern: '*', action: value });
    } else {
      for (const [pattern, action] of Object.entries(value)) {
        rules.push({ permission: key, pattern, action });
      }
    }
  }
  return rules;
}

function buildPermissions(
  rules: PermissionRuleConfig[],
): Record<string, PermissionAction | Record<string, PermissionAction>> {
  const result: Record<string, PermissionAction | Record<string, PermissionAction>> = {};
  for (const rule of rules) {
    if (!rule.permission.trim()) continue;
    if (rule.pattern === '*') {
      result[rule.permission] = rule.action;
    } else {
      const existing = result[rule.permission];
      if (typeof existing === 'object' && existing !== null) {
        existing[rule.pattern] = rule.action;
      } else {
        result[rule.permission] = { [rule.pattern]: rule.action };
      }
    }
  }
  return result;
}

const DEFAULT_CONFIG: SecurityConfigValue = {
  permissions: {
    shell_exec: 'ask',
    mcp_invoke: 'ask',
  },
  approvalTimeoutSeconds: 120,
};

const syncManager = getConfigSyncManager();

function createEmptyRule(): PermissionRuleConfig {
  return { permission: '', pattern: '*', action: 'ask' };
}

const SecurityPolicySection = memo(() => {
  const t = useTranslations('settings.securityPolicy');
  const tCap = useTranslations('cron.capability');

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
        // Parse providerId/model format if needed, or assume it's just the model string
        // Actually, SingleModelSelection requires providerId and model.
        // Let's assume autoReviewModel is stored as "providerId/model" or just "model"
        const parts = cached.autoReviewModel.split('/');
        if (parts.length === 2) {
          setAutoReviewModel({ providerId: parts[0], model: parts[1] });
        } else {
          // Fallback or find provider
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
    [
      rules,
      timeout,
      timeoutBehavior,
      allowedRoots,
      networkAllowlist,
      domainHitlEnabled,
      yoloModeEnabled,
      autoReviewEnabled,
      autoReviewModel,
    ],
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

  const {
    privacyEnabled,
    privacyS2Action,
    privacyS3Action,
    privacyDeepScan,
    privacyRouting,
    setPrivacyEnabled,
    setPrivacyS2Action,
    setPrivacyS3Action,
    setPrivacyDeepScan,
    setPrivacyRouting,
  } = useConfigStore();

  const updateRoutingField = useCallback(
    <K extends keyof PrivacyRoutingConfig>(field: K, value: PrivacyRoutingConfig[K]) => {
      setPrivacyRouting({ ...privacyRouting, [field]: value });
    },
    [privacyRouting, setPrivacyRouting],
  );

  const [testingLocalModel, setTestingLocalModel] = useState(false);

  const handleTestLocalModel = useCallback(async () => {
    if (!privacyRouting?.localModel) return;
    setTestingLocalModel(true);
    try {
      const resp = await fetchWithTimeout(
        '/config/test-local-model',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: privacyRouting.localModel,
            base_url: privacyRouting.localBaseUrl || null,
            api_key: privacyRouting.localApiKey || null,
          }),
        },
        15000,
      );
      const data = await resp.json();
      if (data.success) {
        toast.success(`${t('privacy.routing.testSuccess')} (${data.latency_ms}ms)`);
      } else {
        toast.error(`${t('privacy.routing.testFailed')}: ${data.message}`);
      }
    } catch {
      toast.error(t('privacy.routing.testFailed'));
    } finally {
      setTestingLocalModel(false);
    }
  }, [privacyRouting, t]);

  const handleProfileSelect = useCallback(
    (profile: { config_json: Record<string, unknown> }) => {
      const cfg = profile.config_json;

      // Load permissions into form rules
      const perms = cfg.permissions as Record<string, PermissionAction | Record<string, PermissionAction>> | undefined;
      if (perms) {
        const loadedRules = flattenPermissions(perms);
        setRules(loadedRules);
      }

      // Load path policy
      const pp = cfg.pathPolicy as { allowedRoots?: string[] } | undefined;
      const roots = pp?.allowedRoots ?? [];
      setAllowedRoots(roots);

      // Load timeout
      const t = cfg.approvalTimeoutSeconds as number | undefined;
      if (t !== undefined) setTimeout(t);

      // Load timeout behavior
      const b = cfg.approvalTimeoutBehavior as 'deny' | 'allow' | undefined;
      if (b) setTimeoutBehavior(b);

      // Load network allowlist
      const na = cfg.networkAllowlist as string[] | undefined;
      if (na) setNetworkAllowlist(na);

      // Load domain HITL
      const dh = cfg.domainHitlEnabled as boolean | undefined;
      if (dh !== undefined) setDomainHitlEnabled(dh);

      // Load YOLO mode
      const ym = cfg.yoloModeEnabled as boolean | undefined;
      if (ym !== undefined) setYoloModeEnabled(ym);

      // Load auto review
      const ar = cfg.autoReviewEnabled as boolean | undefined;
      if (ar !== undefined) setAutoReviewEnabled(ar);

      // Save all loaded values
      save({
        rules: perms ? flattenPermissions(perms) : undefined,
        pathPolicy: roots.length > 0 ? { allowedRoots: roots } : undefined,
        timeout: t,
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
        | Record<
            string,
            | import('@/services/config/types').PermissionAction
            | Record<string, import('@/services/config/types').PermissionAction>
          >
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

  if (!loaded) return null;

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Security Profile Selector */}
      <SettingsSection
        title={t('profile.title', { default: 'Security Profile' })}
        description={t('profile.description', { default: 'Select a pre-built security profile or customize below.' })}
      >
        <SecurityProfileSelector onProfileSelect={handleProfileSelect} />
      </SettingsSection>

      {/* NL Policy Generator */}
      <SettingsSection
        title={t('nlGenerator.sectionTitle', { default: 'AI Policy Generator' })}
        description={t('nlGenerator.sectionDesc', {
          default: 'Describe your security requirements in natural language and let AI generate the configuration.',
        })}
      >
        <NLPolicyGenerator
          currentConfig={{
            permissions: buildPermissions(rules),
            approvalTimeoutSeconds: timeout,
            pathPolicy: allowedRoots.length > 0 ? { allowedRoots } : undefined,
            networkAllowlist,
          }}
          onApply={handleNLApply}
        />
      </SettingsSection>

      {/* PII Privacy Protection */}
      <SettingsSection title={t('privacy.title')} description={t('privacy.description')}>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-primary/10 text-primary">
                <IconShield className="h-4 w-4" />
              </div>
              <div>
                <p className="text-sm font-medium text-foreground">{t('privacy.enableLabel')}</p>
                <p className="text-xs text-muted-foreground">{t('privacy.enableDesc')}</p>
              </div>
            </div>
            <Switch checked={privacyEnabled} onCheckedChange={setPrivacyEnabled} />
          </div>

          {privacyEnabled && (
            <div className="ml-11 space-y-3 pt-2 border-t border-border/50">
              <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2">
                <div className="flex items-center gap-2 min-w-[180px]">
                  <IconEye className="h-3.5 w-3.5 text-amber-500" />
                  <span className="text-sm text-foreground">{t('privacy.s2Label')}</span>
                </div>
                <Select value={privacyS2Action} onValueChange={(v: string) => setPrivacyS2Action(v as PIIAction)}>
                  <SelectTrigger className="w-44">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="warn">
                      <span className="flex items-center gap-1.5">
                        <IconShieldAlert className="h-3.5 w-3.5 text-amber-500" />
                        {t('privacy.actionWarn')}
                      </span>
                    </SelectItem>
                    <SelectItem value="pseudonymize">
                      <span className="flex items-center gap-1.5">
                        <IconRefresh className="h-3.5 w-3.5 text-emerald-500" />
                        {t('privacy.actionPseudonymize')}
                      </span>
                    </SelectItem>
                    <SelectItem value="redact">
                      <span className="flex items-center gap-1.5">
                        <IconEyeOff className="h-3.5 w-3.5 text-blue-500" />
                        {t('privacy.actionRedact')}
                      </span>
                    </SelectItem>
                    <SelectItem value="block">
                      <span className="flex items-center gap-1.5">
                        <IconBan className="h-3.5 w-3.5 text-destructive" />
                        {t('privacy.actionBlock')}
                      </span>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2">
                <div className="flex items-center gap-2 min-w-[180px]">
                  <IconEyeOff className="h-3.5 w-3.5 text-destructive" />
                  <span className="text-sm text-foreground">{t('privacy.s3Label')}</span>
                </div>
                <Select value={privacyS3Action} onValueChange={(v: string) => setPrivacyS3Action(v as PIIAction)}>
                  <SelectTrigger className="w-44">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="warn">
                      <span className="flex items-center gap-1.5">
                        <IconShieldAlert className="h-3.5 w-3.5 text-amber-500" />
                        {t('privacy.actionWarn')}
                      </span>
                    </SelectItem>
                    <SelectItem value="pseudonymize">
                      <span className="flex items-center gap-1.5">
                        <IconRefresh className="h-3.5 w-3.5 text-emerald-500" />
                        {t('privacy.actionPseudonymize')}
                      </span>
                    </SelectItem>
                    <SelectItem value="redact">
                      <span className="flex items-center gap-1.5">
                        <IconEyeOff className="h-3.5 w-3.5 text-blue-500" />
                        {t('privacy.actionRedact')}
                      </span>
                    </SelectItem>
                    <SelectItem value="block">
                      <span className="flex items-center gap-1.5">
                        <IconBan className="h-3.5 w-3.5 text-destructive" />
                        {t('privacy.actionBlock')}
                      </span>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {(privacyS2Action === 'pseudonymize' || privacyS3Action === 'pseudonymize') && (
                <div className="flex items-start gap-2 p-2.5 rounded-full bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/50">
                  <IconRefresh className="h-3.5 w-3.5 text-emerald-500 mt-0.5 shrink-0" />
                  <p className="text-xs text-emerald-700 dark:text-emerald-400">{t('privacy.pseudonymizeHint')}</p>
                </div>
              )}

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <IconSearch className="h-3.5 w-3.5 text-primary" />
                  <div>
                    <span className="text-sm text-foreground">{t('privacy.deepScanLabel')}</span>
                    <p className="text-xs text-muted-foreground">{t('privacy.deepScanDesc')}</p>
                  </div>
                </div>
                <Switch checked={privacyDeepScan} onCheckedChange={setPrivacyDeepScan} />
              </div>

              {/* Privacy-Aware Model Routing */}
              <div className="mt-4 pt-4 border-t border-border/50 space-y-3">
                <div className="flex items-center gap-2 mb-2">
                  <Navigation className="h-3.5 w-3.5 text-primary" />
                  <span className="text-sm font-medium text-foreground">{t('privacy.routing.title')}</span>
                </div>
                <p className="text-xs text-muted-foreground mb-3">{t('privacy.routing.description')}</p>

                <div className="space-y-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-medium text-foreground">{t('privacy.routing.localModel')}</label>
                    <div className="flex items-center gap-2">
                      <Input
                        value={privacyRouting?.localModel ?? ''}
                        onChange={(e) => updateRoutingField('localModel', e.target.value || undefined)}
                        placeholder={t('privacy.routing.localModelPlaceholder')}
                        className="text-sm flex-1"
                      />
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={handleTestLocalModel}
                        disabled={testingLocalModel || !privacyRouting?.localModel}
                        className="shrink-0"
                      >
                        {testingLocalModel ? (
                          <IconLoader className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                        ) : (
                          <IconZap className="w-3.5 h-3.5 mr-1.5" />
                        )}
                        {t('privacy.routing.testConnection')}
                      </Button>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="flex flex-col gap-1">
                      <label className="text-xs font-medium text-foreground">{t('privacy.routing.localBaseUrl')}</label>
                      <Input
                        value={privacyRouting?.localBaseUrl ?? ''}
                        onChange={(e) => updateRoutingField('localBaseUrl', e.target.value || undefined)}
                        placeholder={t('privacy.routing.localBaseUrlPlaceholder')}
                        className="text-sm"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-xs font-medium text-foreground">{t('privacy.routing.localApiKey')}</label>
                      <Input
                        type="password"
                        value={privacyRouting?.localApiKey ?? ''}
                        onChange={(e) => updateRoutingField('localApiKey', e.target.value || undefined)}
                        placeholder={t('privacy.routing.localApiKeyPlaceholder')}
                        className="text-sm"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div className="flex flex-col gap-1">
                      <label className="text-xs font-medium text-foreground">{t('privacy.routing.s2Strategy')}</label>
                      <Select
                        value={privacyRouting?.s2Strategy ?? 'cloud_after_redact'}
                        onValueChange={(v: string) => updateRoutingField('s2Strategy', v as PrivacyS2Strategy)}
                      >
                        <SelectTrigger className="text-sm">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="cloud_after_redact">{t('privacy.routing.s2CloudAfterRedact')}</SelectItem>
                          <SelectItem value="local">{t('privacy.routing.s2Local')}</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-xs font-medium text-foreground">{t('privacy.routing.s3Strategy')}</label>
                      <Select
                        value={privacyRouting?.s3Strategy ?? 'local'}
                        onValueChange={(v: string) => updateRoutingField('s3Strategy', v as PrivacyS3Strategy)}
                      >
                        <SelectTrigger className="text-sm">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="local">{t('privacy.routing.s3Local')}</SelectItem>
                          <SelectItem value="block">{t('privacy.routing.s3Block')}</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-xs font-medium text-foreground">
                        {t('privacy.routing.localFallback')}
                      </label>
                      <Select
                        value={privacyRouting?.localFallback ?? 'block'}
                        onValueChange={(v: string) => updateRoutingField('localFallback', v as PrivacyLocalFallback)}
                      >
                        <SelectTrigger className="text-sm">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="block">{t('privacy.routing.fallbackBlock')}</SelectItem>
                          <SelectItem value="force_redact_cloud">
                            {t('privacy.routing.fallbackForceRedactCloud')}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  {!privacyRouting?.localModel &&
                    (privacyRouting?.s2Strategy === 'local' || privacyRouting?.s3Strategy === 'local') && (
                      <div className="flex items-start gap-2 p-2.5 rounded-full bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/50">
                        <IconAlertTriangle className="h-3.5 w-3.5 text-amber-500 mt-0.5 shrink-0" />
                        <p className="text-xs text-amber-700 dark:text-amber-400">
                          {t('privacy.routing.noLocalModelWarning')}
                        </p>
                      </div>
                    )}
                </div>
              </div>

              <AdvancedPiiConfig />
            </div>
          )}
        </div>
      </SettingsSection>

      <SettingsSection title={t('title')} description={t('description')}>
        <div className="space-y-4">
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium text-foreground">{t('approvalTimeout')}</label>
            <p className="text-xs text-muted-foreground">{t('approvalTimeoutDesc')}</p>
            <div className="flex items-center gap-2">
              <Input
                type="number"
                min={10}
                max={600}
                value={timeout}
                onChange={(e) => handleTimeoutChange(e.target.value)}
                className="w-24"
              />
              <span className="text-sm text-muted-foreground">{t('seconds')}</span>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium text-foreground">{t('timeoutBehavior')}</label>
            <p className="text-xs text-muted-foreground">{t('timeoutBehaviorDesc')}</p>
            <Select value={timeoutBehavior} onValueChange={handleTimeoutBehaviorChange}>
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="deny">
                  <span className="flex items-center gap-1.5">
                    <IconBan className="h-3.5 w-3.5 text-destructive" />
                    {t('timeoutDeny')}
                  </span>
                </SelectItem>
                <SelectItem value="allow">
                  <span className="flex items-center gap-1.5">
                    <IconShieldCheck className="h-3.5 w-3.5 text-green-500" />
                    {t('timeoutAllow')}
                  </span>
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </SettingsSection>

      <SettingsSection
        title={t('rulesTitle')}
        description={t('rulesDesc')}
        action={
          <Button variant="outline" size="sm" onClick={handleAddRule}>
            <IconPlus className="h-4 w-4 mr-1" />
            {t('addRule')}
          </Button>
        }
      >
        {rules.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">{t('noRules')}</p>
        ) : (
          <div className="space-y-3">
            {rules.map((rule, idx) => (
              <div
                key={idx}
                className="flex flex-col sm:flex-row items-start sm:items-center gap-2 p-3 rounded-lg border border-border bg-background"
              >
                <Select value={rule.permission} onValueChange={(v) => handleRuleChange(idx, 'permission', v)}>
                  <SelectTrigger className="flex-1 min-w-0">
                    <SelectValue placeholder={t('permissionPlaceholder')} />
                  </SelectTrigger>
                  <SelectContent>
                    {KNOWN_PERMISSIONS.map((perm) => (
                      <SelectItem key={perm} value={perm}>
                        {tCap(perm)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  placeholder={t('patternPlaceholder')}
                  value={rule.pattern}
                  onChange={(e) => handleRuleChange(idx, 'pattern', e.target.value)}
                  className="flex-1 min-w-0 text-sm"
                />
                <Select value={rule.action} onValueChange={(v) => handleRuleChange(idx, 'action', v)}>
                  <SelectTrigger className="w-36 shrink-0">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="allow">
                      <div className="flex items-center gap-2">
                        <IconShieldCheck className="h-3.5 w-3.5 text-green-500" />
                        {t('modeAllow')}
                      </div>
                    </SelectItem>
                    <SelectItem value="ask">
                      <div className="flex items-center gap-2">
                        <IconShieldAlert className="h-3.5 w-3.5 text-amber-500" />
                        {t('modeAsk')}
                      </div>
                    </SelectItem>
                    <SelectItem value="deny">
                      <div className="flex items-center gap-2">
                        <IconBan className="h-3.5 w-3.5 text-destructive" />
                        {t('modeDeny')}
                      </div>
                    </SelectItem>
                  </SelectContent>
                </Select>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => handleRemoveRule(idx)}
                  className="shrink-0 text-muted-foreground hover:text-destructive"
                >
                  <IconTrash className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </SettingsSection>

      <SettingsSection title={t('blacklistTitle')} description={t('blacklistDesc')}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {BUILTIN_BLACKLIST.map((pattern) => (
            <div
              key={pattern}
              className="flex items-center gap-2 px-3 py-2 rounded-full bg-destructive/5 border border-destructive/10"
            >
              <IconBan className="h-3.5 w-3.5 text-destructive shrink-0" />
              <code className="text-xs text-destructive font-mono truncate">{pattern}</code>
            </div>
          ))}
        </div>
      </SettingsSection>

      <SettingsSection title={t('pathPolicyTitle')} description={t('pathPolicyDesc')}>
        <PathPolicyEditor allowedRoots={allowedRoots} onAdd={handleAddRoot} onRemove={handleRemoveRoot} />
      </SettingsSection>

      <DomainAllowlistEditor
        domains={networkAllowlist}
        hitlEnabled={domainHitlEnabled}
        onAddDomain={handleAddDomain}
        onRemoveDomain={handleRemoveDomain}
        onHitlToggle={handleDomainHitlToggle}
      />

      <SettingsSection
        title={t('autoReview.title', { default: 'Smart Intent Guard' })}
        description={t('autoReview.description', {
          default:
            'Use an LLM to automatically review high-risk tool calls (like shell commands or network requests) against your original intent. If the action matches your intent, it is silently approved, reducing interruption fatigue.',
        })}
      >
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-4 p-4 rounded-lg border border-border bg-background">
            <div className="flex-1 space-y-1">
              <div className="flex items-center gap-2">
                <IconShieldCheck className="h-4 w-4 text-green-500" />
                <span className="font-medium">
                  {t('autoReview.enableLabel', { default: 'Enable Smart Intent Guard' })}
                </span>
              </div>
              <p className="text-sm text-muted-foreground">
                {t('autoReview.enableDesc', {
                  default:
                    'When enabled, an LLM will evaluate potentially dangerous tool calls before interrupting you.',
                })}
              </p>
            </div>
            <Switch
              checked={autoReviewEnabled}
              onCheckedChange={handleAutoReviewToggle}
              disabled={!autoReviewModel && enabledModels.length > 0 && !autoReviewEnabled}
            />
          </div>

          <div className="p-4 rounded-lg border border-border bg-muted/30 space-y-3">
            <EnabledModelSelect
              label={t('autoReview.selectModel', { default: 'Select Reviewer Model' })}
              value={autoReviewModel}
              onChange={handleAutoReviewModelChange}
              enabledModels={enabledModels}
              providers={providers}
              placeholder={t('autoReview.selectModelPlaceholder', {
                default: 'Select a fast model (e.g. GPT-4o-mini)',
              })}
            />
            {!autoReviewModel && enabledModels.length > 0 && (
              <div className="flex items-start gap-2 p-2.5 rounded-full bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/50">
                <IconAlertTriangle className="h-3.5 w-3.5 text-amber-500 mt-0.5 shrink-0" />
                <p className="text-xs text-amber-700 dark:text-amber-400">
                  {t('autoReview.noModelWarning', {
                    default:
                      'Please select a reviewer model to enable Smart Intent Guard. Without a dedicated model, the guard cannot function.',
                  })}
                </p>
              </div>
            )}
            {autoReviewEnabled && autoReviewModel && (
              <p className="text-xs text-muted-foreground mt-2">
                {t('autoReview.modelRecommendation', {
                  default:
                    'Recommendation: Use a fast, low-cost model like GPT-4o-mini or Claude 3 Haiku for optimal latency.',
                })}
              </p>
            )}
            {autoReviewEnabled && autoReviewModel && (
              <p className="text-xs text-muted-foreground mt-1">
                {t('autoReview.shellEscalationHint', {
                  default:
                    'Note: In Smart Intent Guard mode, high-risk operations (e.g. shell commands) will be reviewed by the security model even if your permission rules set them to "Allow". Trivially safe commands (ls, cat, git status, etc.) are fast-tracked without LLM review.',
                })}
              </p>
            )}
          </div>
        </div>
      </SettingsSection>

      <SettingsSection
        title={t('yoloMode.title', { default: 'YOLO Mode (Auto-Approve All Tools)' })}
        description={t('yoloMode.description', {
          default:
            'Bypass all tool approval prompts. Use only in trusted environments for development or automation scenarios.',
        })}
      >
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-4 p-4 rounded-lg border border-border bg-background">
            <div className="flex-1 space-y-1">
              <div className="flex items-center gap-2">
                <IconZap className="h-4 w-4 text-amber-500" />
                <span className="font-medium">{t('yoloMode.enableLabel', { default: 'Enable YOLO Mode' })}</span>
              </div>
              <p className="text-sm text-muted-foreground">
                {t('yoloMode.enableDesc', {
                  default: 'When enabled, all tool calls will be automatically approved without user confirmation.',
                })}
              </p>
            </div>
            <Switch checked={yoloModeEnabled} onCheckedChange={handleYoloModeToggle} />
          </div>

          {yoloModeEnabled && (
            <div className="flex items-start gap-3 p-4 rounded-lg border border-destructive/20 bg-destructive/5">
              <IconAlertTriangle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
              <div className="flex-1 space-y-2">
                <p className="text-sm font-medium text-destructive">
                  {t('yoloMode.warning.title', { default: 'Security Warning' })}
                </p>
                <p className="text-sm text-destructive/90">
                  {t('yoloMode.warning.message', {
                    default:
                      'YOLO mode bypasses all security checks. Ensure you trust the AI model and environment before enabling this feature.',
                  })}
                </p>
                <div className="text-xs text-destructive/80 space-y-1 mt-2">
                  <p>
                    •{' '}
                    {t('yoloMode.warning.point1', { default: 'All file operations will execute without confirmation' })}
                  </p>
                  <p>
                    •{' '}
                    {t('yoloMode.warning.point2', {
                      default: 'All network requests will execute without confirmation',
                    })}
                  </p>
                  <p>
                    •{' '}
                    {t('yoloMode.warning.point3', { default: 'All shell commands will execute without confirmation' })}
                  </p>
                </div>
              </div>
            </div>
          )}

          <div className="p-4 rounded-lg border border-border bg-muted/30 space-y-2">
            <div className="flex items-center gap-2 text-sm font-medium">
              <IconShield className="h-4 w-4" />
              <span>{t('yoloMode.useCases.title', { default: 'Recommended Use Cases' })}</span>
            </div>
            <ul className="text-sm text-muted-foreground space-y-1 ml-6">
              <li>• {t('yoloMode.useCases.case1', { default: 'Local development and debugging' })}</li>
              <li>• {t('yoloMode.useCases.case2', { default: 'CI/CD automation pipelines' })}</li>
              <li>• {t('yoloMode.useCases.case3', { default: 'Scheduled tasks and batch processing' })}</li>
              <li>
                •{' '}
                {t('yoloMode.useCases.case4', { default: 'Trusted environments with high confidence in AI behavior' })}
              </li>
            </ul>
          </div>
        </div>
      </SettingsSection>

      <AllowlistSection />
    </div>
  );
});

SecurityPolicySection.displayName = 'SecurityPolicySection';

export default SecurityPolicySection;
