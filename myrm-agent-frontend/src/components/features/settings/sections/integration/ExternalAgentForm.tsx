'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';

import { IconLoader, IconZap } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Switch } from '@/components/primitives/switch';
import { Textarea } from '@/components/primitives/textarea';
import { isLocalMode } from '@/lib/deploy-mode';
import type { ExternalAgentAuthMode, ExternalAgentPermissionMode, ExternalAgentType } from '@/services/config';
import ExternalAgentEnvEditor from './ExternalAgentEnvEditor';
import {
  AGENT_PRESETS,
  PERMISSION_MODE_HINTS,
  PERMISSION_MODE_OPTIONS,
  normalizePermissionMode,
  toDraft,
  type ExternalAgentDraft,
} from './externalAgentModel';

interface ExternalAgentFormProps {
  draft: ExternalAgentDraft;
  /** Adding a new agent: offers the one-click presets. */
  isNew: boolean;
  isTesting: boolean;
  onChange: (next: ExternalAgentDraft) => void;
  onSave: () => void;
  onCancel: () => void;
  onTest: () => void;
}

const ExternalAgentForm = memo(
  ({ draft, isNew, isTesting, onChange, onSave, onCancel, onTest }: ExternalAgentFormProps) => {
    const t = useTranslations('settings.developer.externalAgents');
    const authMode = draft.authMode ?? 'subscription';

    return (
      <div className="border border-border rounded-lg p-4 space-y-4 bg-muted/20">
        {isNew && (
          <div className="flex flex-wrap gap-2">
            <span className="text-xs text-muted-foreground self-center mr-1">{t('presets')}:</span>
            {AGENT_PRESETS.map((preset) => (
              <button
                key={preset.key}
                onClick={() => onChange({ ...toDraft(preset.config), envRows: draft.envRows })}
                className="text-xs px-2.5 py-1 rounded-full border border-border hover:bg-muted transition-colors"
              >
                {t(`preset_${preset.key}` as Parameters<typeof t>[0])}
              </button>
            ))}
          </div>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">{t('name')}</label>
            <Input
              value={draft.name}
              onChange={(e) => onChange({ ...draft, name: e.target.value })}
              placeholder={t('namePlaceholder')}
            />
          </div>
          <div className="space-y-1.5" data-testid="external-agent-type">
            <label className="text-xs font-medium text-muted-foreground">{t('type')}</label>
            <Select value={draft.type} onValueChange={(v: ExternalAgentType) => onChange({ ...draft, type: v })}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="cli" data-testid="external-agent-type-cli">
                  {t('typeCli')}
                </SelectItem>
                <SelectItem value="acp" data-testid="external-agent-type-acp">
                  {t('typeAcp')}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">{t('command')}</label>
          <Input
            value={draft.command}
            onChange={(e) => onChange({ ...draft, command: e.target.value })}
            placeholder={t('commandPlaceholder')}
          />
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">{t('args')}</label>
          <Textarea
            value={(draft.args ?? []).join('\n')}
            onChange={(e) => onChange({ ...draft, args: e.target.value ? e.target.value.split('\n') : [] })}
            placeholder={t('argsPlaceholder')}
            rows={2}
            className="resize-none"
          />
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">{t('descriptionLabel')}</label>
          <Textarea
            value={draft.description ?? ''}
            onChange={(e) => onChange({ ...draft, description: e.target.value })}
            placeholder={t('descriptionPlaceholder')}
            rows={2}
            className="resize-none"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-1.5" data-testid="external-agent-permission-mode">
            <label className="text-xs font-medium text-muted-foreground">{t('permissionMode')}</label>
            <Select
              value={normalizePermissionMode(draft.type, draft.permissionMode)}
              onValueChange={(v: ExternalAgentPermissionMode) => onChange({ ...draft, permissionMode: v })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PERMISSION_MODE_OPTIONS[draft.type].map((option) => (
                  <SelectItem key={option.value} value={option.value} data-testid={`permission-option-${option.value}`}>
                    {t(option.labelKey)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-[11px] text-muted-foreground/60">{t(PERMISSION_MODE_HINTS[draft.type])}</p>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">{t('maxTurns')}</label>
            <Input
              type="number"
              min={1}
              max={200}
              value={draft.maxTurns ?? 25}
              onChange={(e) => onChange({ ...draft, maxTurns: parseInt(e.target.value, 10) || 25 })}
            />
            <p className="text-[11px] text-muted-foreground/60">{t('maxTurnsHint')}</p>
          </div>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">{t('authMode')}</label>
          <Select value={authMode} onValueChange={(v: ExternalAgentAuthMode) => onChange({ ...draft, authMode: v })}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="subscription">{t('authModeSubscription')}</SelectItem>
              <SelectItem value="api_key">{t('authModeApiKey')}</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-[11px] text-muted-foreground/60">{t('authModeHint')}</p>
        </div>

        <ExternalAgentEnvEditor
          rows={draft.envRows}
          authMode={authMode}
          onChange={(envRows) => onChange({ ...draft, envRows })}
        />

        <div className="flex items-center gap-2">
          <Switch checked={draft.enabled} onCheckedChange={(checked) => onChange({ ...draft, enabled: checked })} />
          <span className="text-sm">{t('enabled')}</span>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          {isLocalMode() && (
            <Button variant="ghost" size="sm" onClick={onTest} disabled={isTesting || !draft.command.trim()}>
              {isTesting ? (
                <IconLoader className="w-3.5 h-3.5 mr-1.5 animate-spin" />
              ) : (
                <IconZap className="w-3.5 h-3.5 mr-1.5" />
              )}
              {t('testConnection')}
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={onCancel}>
            {t('cancel')}
          </Button>
          <Button size="sm" onClick={onSave}>
            {t('save')}
          </Button>
        </div>
      </div>
    );
  },
);

ExternalAgentForm.displayName = 'ExternalAgentForm';

export default ExternalAgentForm;
