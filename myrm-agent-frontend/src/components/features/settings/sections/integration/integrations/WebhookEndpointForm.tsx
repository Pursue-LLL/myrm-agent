'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: Settings lifecycle webhook localized copy)
 * - @/components/primitives/* (POS: shared Settings form controls)
 *
 * [OUTPUT]
 * - WebhookEndpointForm: shared create/edit form for lifecycle webhook endpoints
 *
 * [POS]
 * Reusable Settings form for lifecycle outbound webhook create and edit flows.
 */

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Input } from '@/components/primitives/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Key } from 'lucide-react';

export const AVAILABLE_WEBHOOK_EVENT_IDS = [
  'session_completed',
  'session_failed',
  'approval_required',
  'approval_resolved',
  'kanban_task_updated',
  'goal_terminal',
  'subagent_spawned',
  'subagent_merged',
] as const;

export type WebhookEndpointFormValues = {
  name: string;
  url: string;
  secret: string;
  agentId: string | null;
  events: string[];
};

type AgentOption = {
  id: string;
  label: string;
};

type WebhookEndpointFormProps = {
  mode: 'create' | 'edit';
  values: WebhookEndpointFormValues;
  hasExistingSecret?: boolean;
  agentOptions: AgentOption[];
  submitting: boolean;
  onChange: (patch: Partial<WebhookEndpointFormValues>) => void;
  onCancel: () => void;
  onSubmit: () => void;
};

export const WebhookEndpointForm = memo(
  ({
    mode,
    values,
    hasExistingSecret = false,
    agentOptions,
    submitting,
    onChange,
    onCancel,
    onSubmit,
  }: WebhookEndpointFormProps) => {
    const t = useTranslations('settings.lifecycleWebhook');

    const generateSecret = () => {
      const randomBytes = new Uint8Array(16);
      crypto.getRandomValues(randomBytes);
      const hex = Array.from(randomBytes)
        .map((b) => b.toString(16).padStart(2, '0'))
        .join('');
      onChange({ secret: `whsec_${hex}` });
    };

    const toggleEventSelection = (eventId: string) => {
      const nextEvents = values.events.includes(eventId)
        ? values.events.filter((id) => id !== eventId)
        : [...values.events, eventId];
      onChange({ events: nextEvents });
    };

    const secretPlaceholder =
      mode === 'edit' && hasExistingSecret ? t('signingSecretKeepPlaceholder') : t('signingSecretPlaceholder');
    const hasRequiredFields = Boolean(values.name.trim() && values.url.trim() && values.events.length > 0);

    return (
      <div className="space-y-4">
        <h4 className="text-sm font-semibold text-foreground">
          {mode === 'create' ? t('newEndpoint') : t('editEndpoint')}
        </h4>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">{t('endpointName')}</label>
            <Input
              placeholder={t('endpointNamePlaceholder')}
              value={values.name}
              onChange={(e) => onChange({ name: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">{t('payloadUrl')}</label>
            <Input
              placeholder={t('payloadUrlPlaceholder')}
              value={values.url}
              onChange={(e) => onChange({ url: e.target.value })}
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">{t('agentScope')}</label>
          <Select
            value={values.agentId ?? 'all'}
            onValueChange={(value) => onChange({ agentId: value === 'all' ? null : value })}
          >
            <SelectTrigger className="w-full sm:max-w-md">
              <SelectValue placeholder={t('agentScopeAll')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('agentScopeAll')}</SelectItem>
              {agentOptions.map((agent) => (
                <SelectItem key={agent.id} value={agent.id}>
                  {agent.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-[11px] text-muted-foreground">{t('agentScopeHint')}</p>
        </div>

        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
              <Key className="h-3.5 w-3.5" />
              {t('signingSecret')}
            </label>
            <button
              type="button"
              onClick={generateSecret}
              className="text-[11px] text-primary hover:underline cursor-pointer"
            >
              {t('generateRandom')}
            </button>
          </div>
          <Input
            placeholder={secretPlaceholder}
            value={values.secret}
            onChange={(e) => onChange({ secret: e.target.value })}
          />
        </div>

        <div className="space-y-2">
          <label className="text-xs font-medium text-muted-foreground">{t('subscribedEvents')}</label>
          <div className="flex flex-wrap gap-1.5">
            {AVAILABLE_WEBHOOK_EVENT_IDS.map((ev) => {
              const active = values.events.includes(ev);
              return (
                <Badge
                  key={ev}
                  variant={active ? 'default' : 'outline'}
                  className="cursor-pointer transition text-[11px] py-1 px-2.5"
                  onClick={() => toggleEventSelection(ev)}
                >
                  {t(`events.${ev}`)}
                </Badge>
              );
            })}
          </div>
          {values.events.length === 0 ? (
            <p className="text-[11px] text-destructive">{t('eventsRequired')}</p>
          ) : null}
        </div>

        <div className="flex justify-end gap-2 pt-2 border-t border-border/40">
          <Button variant="ghost" size="sm" onClick={onCancel}>
            {t('cancel')}
          </Button>
          <Button size="sm" onClick={onSubmit} disabled={!hasRequiredFields || submitting}>
            {submitting ? t('saving') : mode === 'create' ? t('saveEndpoint') : t('saveChanges')}
          </Button>
        </div>
      </div>
    );
  },
);

WebhookEndpointForm.displayName = 'WebhookEndpointForm';

export default WebhookEndpointForm;
