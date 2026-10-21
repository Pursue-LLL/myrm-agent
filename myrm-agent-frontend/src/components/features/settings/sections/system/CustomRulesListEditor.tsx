'use client';

import React, { memo } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconPlus,
  IconTrash,
  IconShieldCheck,
  IconShieldAlert,
  IconBan,
} from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import type { PermissionAction, PermissionRuleConfig } from '@/services/config/types';
import SettingsSection from '../SettingsSection';
import { KNOWN_PERMISSIONS } from './securityPolicyUtils';

interface CustomRulesListEditorProps {
  rules: PermissionRuleConfig[];
  onAddRule: () => void;
  onRemoveRule: (index: number) => void;
  onRuleChange: (index: number, field: keyof PermissionRuleConfig, value: string) => void;
}

export const CustomRulesListEditor = memo<CustomRulesListEditorProps>(
  ({ rules, onAddRule, onRemoveRule, onRuleChange }) => {
    const t = useTranslations('settings.securityPolicy');
    const tCap = useTranslations('cron.capability');
    const tPerm = useTranslations('settings.securityPolicy.permissionTypes');

    return (
      <SettingsSection
        title={t('rulesTitle')}
        description={t('rulesDesc')}
        action={
          <Button variant="outline" size="sm" onClick={onAddRule}>
            <IconPlus className="h-4 w-4 mr-1" />
            {t('addRule')}
          </Button>
        }
      >
        <div className="rounded-lg border border-border/60 bg-muted/30 p-3 space-y-2 mb-3">
          <p className="text-xs font-medium text-foreground">
            {t('delegationPermissionsGuide.title', { default: 'About delegation permissions' })}
          </p>
          <ul className="text-xs text-muted-foreground space-y-1.5 list-none pl-0">
            <li>
              <span className="font-medium text-foreground">{tPerm('spawn_subagent')}</span>
              {' — '}
              {t('delegationPermissionsGuide.internalDesc', {
                default: 'Spins up a helper agent inside Myrm for research, audit, or parallel work.',
              })}
            </li>
            <li>
              <span className="font-medium text-foreground">{tPerm('invoke_external_agent')}</span>
              {' — '}
              {t('delegationPermissionsGuide.externalDesc', {
                default: 'Runs Claude Code, Codex, or another CLI program on your computer.',
              })}
            </li>
            <li className="text-muted-foreground/90">
              {t('delegationPermissionsGuide.bindingHint', {
                default:
                  'To limit which custom agents a main agent can spawn, configure sub-agent bindings under Settings → Agents → Subagents.',
              })}
            </li>
          </ul>
        </div>

        {rules.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">{t('noRules')}</p>
        ) : (
          <div className="space-y-3">
            {rules.map((rule: PermissionRuleConfig, idx: number) => (
              <div
                key={idx}
                className="flex flex-col sm:flex-row items-start sm:items-center gap-2 p-3 rounded-lg border border-border bg-background"
              >
                <Select value={rule.permission} onValueChange={(v) => onRuleChange(idx, 'permission', v)}>
                  <SelectTrigger className="flex-1 min-w-0">
                    <SelectValue placeholder={t('permissionPlaceholder')} />
                  </SelectTrigger>
                  <SelectContent>
                    {KNOWN_PERMISSIONS.map((perm) => (
                      <SelectItem key={perm} value={perm}>
                        {tPerm(perm, { default: tCap(perm, { default: perm }) })}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Input
                  placeholder={t('patternPlaceholder')}
                  value={rule.pattern}
                  onChange={(e) => onRuleChange(idx, 'pattern', e.target.value)}
                  className="flex-1 min-w-0 text-sm"
                />

                <Select value={rule.action} onValueChange={(v) => onRuleChange(idx, 'action', v as PermissionAction)}>
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
                  onClick={() => onRemoveRule(idx)}
                  className="shrink-0 text-muted-foreground hover:text-destructive"
                >
                  <IconTrash className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </SettingsSection>
    );
  },
);

CustomRulesListEditor.displayName = 'CustomRulesListEditor';
