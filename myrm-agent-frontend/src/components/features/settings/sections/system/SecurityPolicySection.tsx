'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconPlus,
  IconTrash,
  IconShieldCheck,
  IconShieldAlert,
  IconBan,
  IconShield,
  IconZap,
  IconAlertTriangle,
  IconEye,
} from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Switch } from '@/components/primitives/switch';
import type { PermissionRuleConfig } from '@/services/config/types';
import SettingsSection from '../SettingsSection';
import { CapabilitySurfaceMatrixGrid } from './CapabilitySurfaceMatrixGrid';
import { CustomRulesListEditor } from './CustomRulesListEditor';
import { SmartIntentGuardEditor } from './SmartIntentGuardEditor';
import { PathPolicyEditor } from './PathPolicyEditor';
import { DomainAllowlistEditor } from './DomainAllowlistEditor';
import { CommandDenylistEditor } from './CommandDenylistEditor';
import { DomainBlocklistEditor } from './DomainBlocklistEditor';
import AllowlistSection from './AllowlistSection';
import TrustedFoldersSection from './TrustedFoldersSection';
import NLPolicyGenerator from './NLPolicyGenerator';
import SecurityProfileSelector from './SecurityProfileSelector';
import SecurityPrivacyPanel from './SecurityPrivacyPanel';
import { DataFlowDisclosurePanel } from './DataFlowDisclosurePanel';
import { DualTrackAuditDashboard } from './DualTrackAuditDashboard';
import { BUILTIN_BLACKLIST, buildPermissions } from './securityPolicyUtils';
import { useSecurityPolicy } from './useSecurityPolicy';

const SecurityPolicySection = memo(() => {
  const t = useTranslations('settings.securityPolicy');
  const tCap = useTranslations('cron.capability');
  const tPerm = useTranslations('settings.securityPolicy.permissionTypes');

  const policy = useSecurityPolicy(t);

  if (!policy.loaded) {
    return null;
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <SettingsSection
        title={t('profile.title', { default: 'Security Profile' })}
        description={t('profile.description', { default: 'Select a pre-built security profile or customize below.' })}
      >
        <SecurityProfileSelector onProfileSelect={policy.handleProfileSelect} />
      </SettingsSection>

      {policy.managedPolicyActive && (
        <div className="rounded-lg border border-border bg-muted/40 p-4 space-y-2">
          <p className="text-sm font-medium">
            {t('managedPolicy.orgActiveTitle', {
              default: 'Organization approval policy is active',
            })}
          </p>
          <p className="text-xs text-muted-foreground">
            {t('managedPolicy.orgActiveDesc', {
              default:
                'Your admin may require Smart Intent Guard or disable allowlist shortcuts for specific agent models. Configure agents in AI Core when using protected models.',
            })}
          </p>
          {(policy.managedPolicyEffective.forceAutoReviewForModels?.length ?? 0) > 0 && (
            <p className="text-xs text-muted-foreground font-mono">
              {t('managedPolicy.forceModels', {
                default: 'Forced review models: {patterns}',
                patterns: policy.managedPolicyEffective.forceAutoReviewForModels?.join(', ') ?? '',
              })}
            </p>
          )}
          {(policy.managedPolicyEffective.ignoreAllowlistForModels?.length ?? 0) > 0 && (
            <p className="text-xs text-muted-foreground font-mono">
              {t('managedPolicy.ignoreAllowlistModels', {
                default: 'Allowlist ignored for: {patterns}',
                patterns: policy.managedPolicyEffective.ignoreAllowlistForModels?.join(', ') ?? '',
              })}
            </p>
          )}
        </div>
      )}

      <SettingsSection
        title={t('nlGenerator.sectionTitle', { default: 'AI Policy Generator' })}
        description={t('nlGenerator.sectionDesc', {
          default: 'Describe your security requirements in natural language and let AI generate the configuration.',
        })}
      >
        <NLPolicyGenerator
          currentConfig={{
            permissions: buildPermissions(policy.rules),
            approvalTimeoutSeconds: policy.timeout,
            pathPolicy: policy.allowedRoots.length > 0 ? { allowedRoots: policy.allowedRoots } : undefined,
            networkAllowlist: policy.networkAllowlist,
            networkBlocklist: policy.networkBlocklist,
            commandDenylist: policy.commandDenylist,
          }}
          onApply={policy.handleNLApply}
        />
      </SettingsSection>

      <SecurityPrivacyPanel />

      <DataFlowDisclosurePanel />

      <DualTrackAuditDashboard />

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
                value={policy.timeout}
                onChange={(e) => policy.handleTimeoutChange(e.target.value)}
                className="w-24"
              />
              <span className="text-sm text-muted-foreground">{t('seconds')}</span>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium text-foreground">{t('timeoutBehavior')}</label>
            <p className="text-xs text-muted-foreground">{t('timeoutBehaviorDesc')}</p>
            <Select value={policy.timeoutBehavior} onValueChange={policy.handleTimeoutBehaviorChange}>
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
        title={t('capabilityMatrix.title', { default: 'Capability Surface Matrix (Always / Ask / Deny)' })}
        description={t('capabilityMatrix.desc', {
          default:
            'Fine-grained tri-state posture governing knowledge bases, outbound network, candidate artifacts, remote tools, and workspace filesystem.',
        })}
      >
        <CapabilitySurfaceMatrixGrid
          matrix={policy.capabilityMatrix}
          onChange={policy.handleCapabilityChange}
          onApplyPreset={policy.handleCapabilityPresetApply}
        />
      </SettingsSection>

      <CustomRulesListEditor
        rules={policy.rules}
        onAddRule={policy.handleAddRule}
        onRemoveRule={policy.handleRemoveRule}
        onRuleChange={policy.handleRuleChange}
      />

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
        <PathPolicyEditor
          allowedRoots={policy.allowedRoots}
          onAdd={policy.handleAddRoot}
          onRemove={policy.handleRemoveRoot}
        />
      </SettingsSection>

      <DomainAllowlistEditor
        domains={policy.networkAllowlist}
        hitlEnabled={policy.domainHitlEnabled}
        onAddDomain={policy.handleAddDomain}
        onRemoveDomain={policy.handleRemoveDomain}
        onHitlToggle={policy.handleDomainHitlToggle}
      />

      <DomainBlocklistEditor
        domains={policy.networkBlocklist}
        onAddDomain={policy.handleAddBlockedDomain}
        onRemoveDomain={policy.handleRemoveBlockedDomain}
      />

      <CommandDenylistEditor
        patterns={policy.commandDenylist}
        onAddPattern={policy.handleAddCommandPattern}
        onRemovePattern={policy.handleRemoveCommandPattern}
      />

      <SettingsSection
        title={t('injectionPolicy.title', { default: 'Prompt Injection Guard' })}
        description={t('injectionPolicy.description', {
          default:
            'Block detected prompt injection attacks instead of only logging them. IM and Cron channels default to blocking mode regardless of this setting.',
        })}
      >
        <div className="flex items-center justify-between gap-4 p-4 rounded-lg border border-border bg-background">
          <div className="flex-1 space-y-1">
            <div className="flex items-center gap-2">
              <IconShieldAlert className="h-4 w-4 text-amber-500" />
              <span className="font-medium">
                {t('injectionPolicy.enableLabel', { default: 'Enable Fail-Closed Blocking' })}
              </span>
            </div>
            <p className="text-sm text-muted-foreground">
              {t('injectionPolicy.enableDesc', {
                default:
                  'When enabled, high-threat prompt injection patterns (score >= 0.7) will be blocked and replaced with a safe placeholder, preventing the LLM from processing malicious input.',
              })}
            </p>
          </div>
          <Switch
            checked={policy.injectionPolicy === 'fail_closed'}
            onCheckedChange={policy.handleInjectionPolicyToggle}
          />
        </div>
      </SettingsSection>

      <SmartIntentGuardEditor
        autoReviewEnabled={policy.autoReviewEnabled}
        autoReviewModel={policy.autoReviewModel}
        enabledModels={policy.enabledModels}
        providers={policy.providers}
        onToggle={policy.handleAutoReviewToggle}
        onModelChange={policy.handleAutoReviewModelChange}
      />

      <SettingsSection
        title={t('planReview.title', { default: 'Plan Review' })}
        description={t('planReview.description', {
          default:
            "Review and approve the AI's task plan before execution begins. Helps catch mistakes early — before any files are modified.",
        })}
      >
        <div className="flex items-center justify-between gap-4 p-4 rounded-lg border border-border bg-background">
          <div className="flex-1 space-y-1">
            <div className="flex items-center gap-2">
              <IconEye className="h-4 w-4 text-blue-500" />
              <span className="font-medium">{t('planReview.enableLabel', { default: 'Enable Plan Review' })}</span>
            </div>
            <p className="text-sm text-muted-foreground">
              {t('planReview.enableDesc', {
                default:
                  'When enabled, the AI will pause and show you the plan for review before starting complex tasks (3 or more steps).',
              })}
            </p>
          </div>
          <Switch
            checked={policy.planConfirmEnabled}
            onCheckedChange={policy.handlePlanConfirmToggle}
            disabled={policy.yoloModeEnabled}
          />
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
            <Switch
              checked={policy.yoloModeEnabled}
              onCheckedChange={policy.handleYoloModeToggle}
              disabled={policy.managedDisableYolo}
            />
          </div>
          {policy.managedDisableYolo && (
            <p className="text-xs text-muted-foreground px-1">
              {t('managedPolicy.yoloLocked', {
                default: 'YOLO mode is disabled by your organization policy.',
              })}
            </p>
          )}

          {policy.yoloModeEnabled && (
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

      {policy.managedDisableAllowAlways && (
        <p className="text-xs text-muted-foreground px-1">
          {t('managedPolicy.allowAlwaysDisabled', {
            default: 'Your organization disabled saving permanent allowlist entries from approval prompts.',
          })}
        </p>
      )}

      <AllowlistSection />

      <TrustedFoldersSection />
    </div>
  );
});

SecurityPolicySection.displayName = 'SecurityPolicySection';

export default SecurityPolicySection;
