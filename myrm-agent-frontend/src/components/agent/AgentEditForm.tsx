'use client';

import { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import useSWR from 'swr';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import TextareaAutosize from 'react-textarea-autosize';
import { getAgent, createAgent, updateAgent, Agent, type AgentType } from '@/services/agent';
import { Loader2, Users } from 'lucide-react';
import { Select, SelectContent, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { toast } from '@/hooks/shared/useToast';
import { isRiskHeldError } from '@/services/riskHeldToast';
import { CommandBindingsEditor } from '@/components/agent/CommandBindingsEditor';
import { AgentEditAvatarField } from '@/components/agent/AgentEditAvatarField';
import { AgentEditBrowserSettings } from '@/components/agent/AgentEditBrowserSettings';
import { AgentEditResponsibilityFields } from '@/components/agent/AgentEditResponsibilityFields';
import { AgentEditSessionPolicy } from '@/components/agent/AgentEditSessionPolicy';
import { DescribedSelectItem } from '@/components/agent/DescribedSelectItem';
import {
  agentSchema,
  buildAgentPayload,
  EMPTY_EXTRA_FIELDS,
  EMPTY_FORM_VALUES,
  extraFieldsFromAgent,
  formValuesFromAgent,
  type AgentExtraFields,
  type AgentFormData,
} from '@/components/agent/agentEditFormModel';

interface AgentEditFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agentId?: string | null;
  onSaveSuccess: () => void;
}

export function AgentEditForm({ open, onOpenChange, agentId, onSaveSuccess }: AgentEditFormProps) {
  const t = useTranslations('Agent');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [extra, setExtra] = useState<AgentExtraFields>(EMPTY_EXTRA_FIELDS);
  const patchExtra = useCallback((patch: Partial<AgentExtraFields>) => setExtra((prev) => ({ ...prev, ...patch })), []);

  const { data: agent, isLoading } = useSWR<Agent>(open && agentId ? `getAgent-${agentId}` : null, () => {
    if (!agentId) {
      throw new Error('Agent id missing for agent fetch');
    }
    return getAgent(agentId, true);
  });

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors },
  } = useForm<AgentFormData>({
    resolver: zodResolver(agentSchema),
    defaultValues: EMPTY_FORM_VALUES,
  });

  const avatarUrl = watch('avatar_url');
  const name = watch('name');

  useEffect(() => {
    if (!open) {
      return;
    }
    if (agent) {
      reset(formValuesFromAgent(agent));
      setExtra(extraFieldsFromAgent(agent));
    } else if (!agentId) {
      reset(EMPTY_FORM_VALUES);
      setExtra(EMPTY_EXTRA_FIELDS);
    }
  }, [open, agent, agentId, reset]);

  const onSubmit = async (data: AgentFormData) => {
    setIsSubmitting(true);
    try {
      const payload = buildAgentPayload(data, extra);
      if (agentId) {
        await updateAgent(agentId, payload);
      } else {
        await createAgent(payload);
      }
      onSaveSuccess();
    } catch (error) {
      console.error('Failed to save agent:', error);
      if (!isRiskHeldError(error)) {
        toast.error(t('saveError'));
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{agentId ? t('edit.title') : t('create.title')}</DialogTitle>
        </DialogHeader>

        {isLoading ? (
          <div className="flex justify-center items-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-6 py-4">
            <AgentEditAvatarField
              agentId={agentId}
              avatarUrl={avatarUrl}
              name={name}
              onAvatarChange={(url) => setValue('avatar_url', url)}
            />

            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name">
                  {t('form.name')} <span className="text-destructive-text">*</span>
                </Label>
                <Input id="name" {...register('name')} placeholder={t('form.namePlaceholder')} />
                {errors.name && <p className="text-sm text-destructive-text">{errors.name.message}</p>}
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">{t('form.description')}</Label>
                <Input id="description" {...register('description')} placeholder={t('form.descriptionPlaceholder')} />
                {errors.description && <p className="text-sm text-destructive-text">{errors.description.message}</p>}
              </div>

              <AgentEditResponsibilityFields value={extra} onChange={patchExtra} />

              <div className="space-y-2">
                <Label htmlFor="agent_type" className="flex items-center gap-1.5">
                  <Users size={14} className="text-muted-foreground" />
                  {t('form.agentType')}
                </Label>
                <Select value={extra.agentType} onValueChange={(v) => patchExtra({ agentType: v as AgentType })}>
                  <SelectTrigger id="agent_type" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <DescribedSelectItem
                      value="individual"
                      label={t('form.agentTypeIndividual')}
                      description={t('form.agentTypeIndividualDesc')}
                    />
                    <DescribedSelectItem
                      value="team"
                      label={t('form.agentTypeTeam')}
                      description={t('form.agentTypeTeamDesc')}
                    />
                  </SelectContent>
                </Select>
                {extra.agentType === 'team' && (
                  <p className="text-xs text-muted-foreground mt-1">{t('form.agentTypeTeamHint')}</p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="system_prompt">{t('form.systemPrompt')}</Label>
                <TextareaAutosize
                  id="system_prompt"
                  {...register('system_prompt')}
                  minRows={4}
                  maxRows={12}
                  className="flex w-full rounded-full border border-input bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 resize-none"
                  placeholder={t('form.systemPromptPlaceholder')}
                />
                {errors.system_prompt && (
                  <p className="text-sm text-destructive-text">{errors.system_prompt.message}</p>
                )}
              </div>

              <CommandBindingsEditor
                value={extra.commandBindings}
                onChange={(commandBindings) => patchExtra({ commandBindings })}
              />

              <AgentEditBrowserSettings value={extra} onChange={patchExtra} />

              <AgentEditSessionPolicy value={extra} onChange={patchExtra} />
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t('cancel')}
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t('save')}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
