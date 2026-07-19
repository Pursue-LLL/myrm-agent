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
import EnabledModelSelect from '../../default-model/EnabledModelSelect';
import type { PermissionRuleConfig } from '@/services/config/types';
import SettingsSection from '../SettingsSection';
import { PathPolicyEditor } from './PathPolicyEditor';
import { DomainAllowlistEditor } from './DomainAllowlistEditor';
import { DomainBlocklistEditor } from './DomainBlocklistEditor';
import AllowlistSection from './AllowlistSection';
import NLPolicyGenerator from './NLPolicyGenerator';
import SecurityProfileSelector from './SecurityProfileSelector';
import SecurityPrivacyPanel from './SecurityPrivacyPanel';
import { BUILTIN_BLACKLIST, KNOWN_PERMISSIONS, buildPermissions } from './securityPolicyUtils';
import { useSecurityPolicy } from './useSecurityPolicy';

const SecurityPolicySection = memo(() => {
  const t = useTranslations('settings.securityPolicy');
  const tCap = useTranslations('cron.capability');

  const policy = useSecurityPolicy(t);

  if (!policy.loaded) return null;

  return (
    <div className="space-y-6 max-w-4xl">
      <SettingsSection
        title={t('profile.title', { default: 'Security Profile' })}
        description={t('profile.description', { default: 'Select a pre-built security profile or customize below.' })}
      >
        <SecurityProfileSelector onProfileSelect={policy.handleProfileSelect} />
      </SettingsSection>

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
          }}
          onApply={policy.handleNLApply}
        />
      </SettingsSection>

      <SecurityPrivacyPanel />

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
        title={t('rulesTitle')}
        description={t('rulesDesc')}
        action={
          <Button variant="outline" size="sm" onClick={policy.handleAddRule}>
            <IconPlus className="h-4 w-4 mr-1" />
            {t('addRule')}
          </Button>
        }
      >
        {policy.rules.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">{t('noRules')}</p>
        ) : (
          <div className="space-y-3">
            {policy.rules.map((rule: PermissionRuleConfig, idx: number) => (
              <div
                key={idx}
                className="flex flex-col sm:flex-row items-start sm:items-center gap-2 p-3 rounded-lg border border-border bg-background"
              >
                <Select value={rule.permission} onValueChange={(v) => policy.handleRuleChange(idx, 'permission', v)}>
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
                  onChange={(e) => policy.handleRuleChange(idx, 'pattern', e.target.value)}
                  className="flex-1 min-w-0 text-sm"
                />
                <Select value={rule.action} onValueChange={(v) => policy.handleRuleChange(idx, 'action', v)}>
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
                  onClick={() => policy.handleRemoveRule(idx)}
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
              checked={policy.autoReviewEnabled}
              onCheckedChange={policy.handleAutoReviewToggle}
              disabled={!policy.autoReviewModel && policy.enabledModels.length > 0 && !policy.autoReviewEnabled}
            />
          </div>

          <div className="p-4 rounded-lg border border-border bg-muted/30 space-y-3">
            <EnabledModelSelect
              label={t('autoReview.selectModel', { default: 'Select Reviewer Model' })}
              value={policy.autoReviewModel}
              onChange={policy.handleAutoReviewModelChange}
              enabledModels={policy.enabledModels}
              providers={policy.providers}
              placeholder={t('autoReview.selectModelPlaceholder', {
                default: 'Select a fast model (e.g. GPT-4o-mini)',
              })}
            />
            {!policy.autoReviewModel && policy.enabledModels.length > 0 && (
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
            {policy.autoReviewEnabled && policy.autoReviewModel && (
              <p className="text-xs text-muted-foreground mt-2">
                {t('autoReview.modelRecommendation', {
                  default:
                    'Recommendation: Use a fast, low-cost model like GPT-4o-mini or Claude 3 Haiku for optimal latency.',
                })}
              </p>
            )}
            {policy.autoReviewEnabled && policy.autoReviewModel && (
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
        title={t('planReview.title', { default: 'Plan Review' })}
        description={t('planReview.description', {
          default:
            'Review and approve the AI\'s task plan before execution begins. Helps catch mistakes early — before any files are modified.',
        })}
      >
        <div className="flex items-center justify-between gap-4 p-4 rounded-lg border border-border bg-background">
          <div className="flex-1 space-y-1">
            <div className="flex items-center gap-2">
              <IconEye className="h-4 w-4 text-blue-500" />
              <span className="font-medium">
                {t('planReview.enableLabel', { default: 'Enable Plan Review' })}
              </span>
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
            <Switch checked={policy.yoloModeEnabled} onCheckedChange={policy.handleYoloModeToggle} />
          </div>

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
                    • {t('yoloMode.warning.point1', { default: 'All file operations will execute without confirmation' })}
                  </p>
                  <p>
                    • {t('yoloMode.warning.point2', { default: 'All network requests will execute without confirmation' })}
                  </p>
                  <p>
                    • {t('yoloMode.warning.point3', { default: 'All shell commands will execute without confirmation' })}
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
                • {t('yoloMode.useCases.case4', { default: 'Trusted environments with high confidence in AI behavior' })}
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
