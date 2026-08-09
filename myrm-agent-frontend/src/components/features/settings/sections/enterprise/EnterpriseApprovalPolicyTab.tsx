'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Switch } from '@/components/primitives/switch';
import { getApiUrl } from '@/lib/api';

interface ApprovalPolicyState {
  ignoreAllowlistForModels: string[];
  forceAutoReviewForModels: string[];
  disableYolo: boolean;
  disableAllowAlways: boolean;
}

const EMPTY_POLICY: ApprovalPolicyState = {
  ignoreAllowlistForModels: [],
  forceAutoReviewForModels: [],
  disableYolo: false,
  disableAllowAlways: false,
};

const EnterpriseApprovalPolicyTab = memo(() => {
  const t = useTranslations('settings.enterprise');
  const [policy, setPolicy] = useState<ApprovalPolicyState>(EMPTY_POLICY);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [ignoreInput, setIgnoreInput] = useState('');
  const [forceInput, setForceInput] = useState('');

  const orgId = typeof window !== 'undefined' ? localStorage.getItem('org_id') || '' : '';

  const fetchPolicy = useCallback(async () => {
    if (!orgId) {
      setLoading(false);
      return;
    }
    try {
      const res = await fetch(getApiUrl(`/api/enterprise/org/${orgId}/approval-policy`));
      if (res.ok) {
        const data = (await res.json()) as ApprovalPolicyState;
        setPolicy({
          ignoreAllowlistForModels: data.ignoreAllowlistForModels ?? [],
          forceAutoReviewForModels: data.forceAutoReviewForModels ?? [],
          disableYolo: Boolean(data.disableYolo),
          disableAllowAlways: Boolean(data.disableAllowAlways),
        });
      }
    } catch {
      toast.error(t('approvalPolicy.loadFailed', { default: 'Failed to load approval policy' }));
    } finally {
      setLoading(false);
    }
  }, [orgId, t]);

  useEffect(() => {
    void fetchPolicy();
  }, [fetchPolicy]);

  const handleSave = async () => {
    if (!orgId) return;
    setSaving(true);
    try {
      const res = await fetch(getApiUrl(`/api/enterprise/org/${orgId}/approval-policy`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ignore_allowlist_for_models: policy.ignoreAllowlistForModels,
          force_auto_review_for_models: policy.forceAutoReviewForModels,
          disable_yolo: policy.disableYolo,
          disable_allow_always: policy.disableAllowAlways,
        }),
      });
      if (!res.ok) {
        throw new Error(await res.text());
      }
      const saved = (await res.json()) as ApprovalPolicyState & {
        fanout?: { failed?: number; synced?: number };
      };
      toast.success(t('approvalPolicy.saved', { default: 'Approval policy saved' }));
      if ((saved.fanout?.failed ?? 0) > 0) {
        toast.warning(
          t('approvalPolicy.fanoutPartial', {
            default: 'Policy saved, but {failed} member sandbox(es) did not sync. Active members may need to refresh.',
            failed: String(saved.fanout?.failed ?? 0),
          }),
        );
      }
      await fetchPolicy();
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : t('approvalPolicy.saveFailed', { default: 'Failed to save approval policy' }),
      );
    } finally {
      setSaving(false);
    }
  };

  const addPattern = (field: 'ignoreAllowlistForModels' | 'forceAutoReviewForModels', raw: string) => {
    const pattern = raw.trim();
    if (!pattern) return;
    setPolicy((prev) => {
      const list = prev[field];
      if (list.includes(pattern)) return prev;
      return { ...prev, [field]: [...list, pattern] };
    });
  };

  const removePattern = (
    field: 'ignoreAllowlistForModels' | 'forceAutoReviewForModels',
    pattern: string,
  ) => {
    setPolicy((prev) => ({
      ...prev,
      [field]: prev[field].filter((entry) => entry !== pattern),
    }));
  };

  if (loading) {
    return <div className="animate-pulse h-32 bg-muted rounded" />;
  }

  if (!orgId) {
    return (
      <div className="text-center text-muted-foreground py-8">
        {t('approvalPolicy.noOrg', { default: 'Organization not configured' })}
      </div>
    );
  }

  const renderPatternList = (
    field: 'ignoreAllowlistForModels' | 'forceAutoReviewForModels',
    title: string,
    description: string,
    inputValue: string,
    setInputValue: (value: string) => void,
  ) => (
    <div className="space-y-3 p-4 rounded-lg border border-border bg-background">
      <div>
        <h4 className="text-sm font-medium">{title}</h4>
        <p className="text-xs text-muted-foreground mt-1">{description}</p>
      </div>
      <div className="flex gap-2">
        <Input
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          placeholder="e.g. claude-opus*"
          className="text-sm"
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              addPattern(field, inputValue);
              setInputValue('');
            }
          }}
        />
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={() => {
            addPattern(field, inputValue);
            setInputValue('');
          }}
        >
          {t('approvalPolicy.addPattern', { default: 'Add' })}
        </Button>
      </div>
      {policy[field].length > 0 && (
        <div className="flex flex-wrap gap-2">
          {policy[field].map((pattern) => (
            <button
              key={pattern}
              type="button"
              className="text-xs font-mono bg-muted px-2 py-1 rounded hover:bg-muted/80"
              onClick={() => removePattern(field, pattern)}
              title={t('approvalPolicy.removePattern', { default: 'Click to remove' })}
            >
              {pattern} ×
            </button>
          ))}
        </div>
      )}
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h3 className="text-sm font-medium">
          {t('approvalPolicy.title', { default: 'Approval Policy' })}
        </h3>
        <p className="text-xs text-muted-foreground">
          {t('approvalPolicy.description', {
            default:
              'Set organization-wide security floors for tool approvals. Changes apply to member sandboxes shortly after save.',
          })}
        </p>
        <p className="text-xs text-muted-foreground/80">
          {t('approvalPolicy.patternHint', {
            default: 'Use the model slug only (e.g. claude-opus-4), not the provider prefix.',
          })}
        </p>
      </div>

      {renderPatternList(
        'ignoreAllowlistForModels',
        t('approvalPolicy.ignoreAllowlistTitle', {
          default: 'Ignore prefix allowlist (by model)',
        }),
        t('approvalPolicy.ignoreAllowlistDesc', {
          default:
            'Matched models cannot auto-approve via saved allowlist shortcuts; they follow Smart Intent Guard or manual approval.',
        }),
        ignoreInput,
        setIgnoreInput,
      )}

      {renderPatternList(
        'forceAutoReviewForModels',
        t('approvalPolicy.forceAutoReviewTitle', {
          default: 'Force Smart Intent Guard (by model)',
        }),
        t('approvalPolicy.forceAutoReviewDesc', {
          default:
            'Matched models always run Smart Intent Guard before risky tool calls, even if members turned it off.',
        }),
        forceInput,
        setForceInput,
      )}

      <div className="space-y-4 p-4 rounded-lg border border-border bg-background">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium">
              {t('approvalPolicy.disableYoloTitle', { default: 'Disable YOLO mode' })}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              {t('approvalPolicy.disableYoloDesc', {
                default: 'Members cannot enable auto-approve-all for any agent.',
              })}
            </p>
          </div>
          <Switch
            checked={policy.disableYolo}
            onCheckedChange={(checked) => setPolicy((prev) => ({ ...prev, disableYolo: checked }))}
          />
        </div>
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium">
              {t('approvalPolicy.disableAllowAlwaysTitle', { default: 'Disable Always Allow' })}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              {t('approvalPolicy.disableAllowAlwaysDesc', {
                default: 'Hide and block saving permanent allowlist entries from approval prompts.',
              })}
            </p>
          </div>
          <Switch
            checked={policy.disableAllowAlways}
            onCheckedChange={(checked) =>
              setPolicy((prev) => ({ ...prev, disableAllowAlways: checked }))
            }
          />
        </div>
      </div>

      <Button onClick={handleSave} disabled={saving}>
        {saving
          ? t('approvalPolicy.saving', { default: 'Saving…' })
          : t('approvalPolicy.save', { default: 'Save policy' })}
      </Button>
    </div>
  );
});

EnterpriseApprovalPolicyTab.displayName = 'EnterpriseApprovalPolicyTab';

export default EnterpriseApprovalPolicyTab;
