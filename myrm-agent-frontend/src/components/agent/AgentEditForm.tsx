'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import useSWR from 'swr';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { AgentAvatar } from '@/components/agent/AgentAvatar';
import { AgentIcon, AGENT_ICON_REGISTRY } from '@/components/agent/agent-icons';
import TextareaAutosize from 'react-textarea-autosize';
import {
  getAgent,
  createAgent,
  updateAgent,
  Agent,
  CommandBindingConfig,
  type AgentType,
  type AgentSessionPolicy,
  type SessionResetMode,
  type ToolGatewayConfigDTO,
} from '@/services/agent';
import { AlertCircle, Loader2, Upload, Users } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Switch } from '@/components/primitives/switch';
import { cn } from '@/lib/utils';
import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';
import { toast } from '@/hooks/useToast';
import { CommandBindingsEditor } from '@/components/agent/CommandBindingsEditor';

// Zod Schema for validation
const agentSchema = z.object({
  name: z.string().min(1, 'Name is required').max(50, 'Name must be less than 50 characters'),
  description: z.string().max(200, 'Description must be less than 200 characters').optional(),
  system_prompt: z.string().max(10000, 'System prompt is too long').optional(),
  avatar_url: z.string().optional(),
});

type AgentFormData = z.infer<typeof agentSchema>;

interface AgentEditFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agentId?: string | null;
  onSaveSuccess: () => void;
}

export function AgentEditForm({ open, onOpenChange, agentId, onSaveSuccess }: AgentEditFormProps) {
  const t = useTranslations('Agent');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false);
  const [commandBindings, setCommandBindings] = useState<CommandBindingConfig[]>([]);
  const [agentType, setAgentType] = useState<AgentType>('individual');
  const [sessionPolicyEnabled, setSessionPolicyEnabled] = useState(false);
  const [sessionPolicy, setSessionPolicy] = useState<AgentSessionPolicy>({
    mode: 'daily',
    daily_reset_hour: 4,
    idle_minutes: 120,
  });
  const [toolGatewayConfig, setToolGatewayConfig] = useState<ToolGatewayConfigDTO>({
    use_gateway: false,
  });
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [browserEngine, setBrowserEngine] = useState<string>('chromium_patchright');
  const [browserSource, setBrowserSource] = useState<string>('auto');

  const { data: agent, isLoading } = useSWR<Agent>(open && agentId ? `getAgent-${agentId}` : null, () =>
    getAgent(agentId!, true),
  );

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors },
  } = useForm<AgentFormData>({
    resolver: zodResolver(agentSchema),
    defaultValues: {
      name: '',
      description: '',
      system_prompt: '',
      avatar_url: '',
    },
  });

  const avatarUrl = watch('avatar_url');
  const name = watch('name');

  useEffect(() => {
    if (open) {
      if (agent) {
        reset({
          name: agent.name,
          description: agent.description || '',
          system_prompt: agent.system_prompt || '',
          avatar_url: agent.avatar_url || '',
        });
        setCommandBindings(agent.command_bindings || []);
        setAgentType(agent.agent_type || 'individual');
        if (agent.session_policy) {
          setSessionPolicyEnabled(true);
          setSessionPolicy(agent.session_policy);
        } else {
          setSessionPolicyEnabled(false);
          setSessionPolicy({ mode: 'daily', daily_reset_hour: 4, idle_minutes: 120 });
        }
        if (agent.tool_gateway_config) {
          setToolGatewayConfig(agent.tool_gateway_config);
        } else {
          setToolGatewayConfig({ use_gateway: false });
        }
        setBrowserEngine(agent.browser_engine || 'chromium_patchright');
        setBrowserSource(agent.browser_source || 'auto');
      } else if (!agentId) {
        reset({
          name: '',
          description: '',
          system_prompt: '',
          avatar_url: '',
        });
        setCommandBindings([]);
        setAgentType('individual');
        setSessionPolicyEnabled(false);
        setSessionPolicy({ mode: 'daily', daily_reset_hour: 4, idle_minutes: 120 });
        setToolGatewayConfig({ use_gateway: false });
        setBrowserEngine('chromium_patchright');
      }
    }
  }, [open, agent, agentId, reset]);

  const onSubmit = async (data: AgentFormData) => {
    setIsSubmitting(true);
    try {
      const validBindings = commandBindings.filter((b) => b.command_name && b.skill_id);
      const payload = {
        ...data,
        agent_type: agentType,
        command_bindings: validBindings.length > 0 ? validBindings : null,
        session_policy: sessionPolicyEnabled ? sessionPolicy : null,
        tool_gateway_config: toolGatewayConfig,
        browser_engine: browserEngine,
        browser_source: browserSource === 'auto' ? null : browserSource,
      };
      if (agentId) {
        await updateAgent(agentId, payload);
      } else {
        await createAgent(payload);
      }
      onSaveSuccess();
    } catch (error) {
      console.error('Failed to save agent:', error);
      toast.error(t('saveError', { fallback: 'Failed to save agent.' }));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleAvatarClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Local preview instantly
    const objectUrl = URL.createObjectURL(file);
    setValue('avatar_url', objectUrl);

    if (!agentId) {
      // If it's a new agent, we can't upload to /api/v1/user-agents/{id}/avatar yet.
      // We would need to either upload to a generic endpoint or wait until creation.
      // For now, we just keep the object URL (which won't persist across reloads).
      // A full implementation would upload to a temp storage or create the agent first.
      return;
    }

    setIsUploadingAvatar(true);
    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/${agentId}/avatar`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
        },
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Failed to upload avatar');
      }

      const result = await response.json();
      setValue('avatar_url', result.data.avatar_url);
    } catch (error) {
      console.error('Avatar upload failed:', error);
      toast.error(t('avatar.error', { fallback: 'Failed to upload avatar.' }));
    } finally {
      setIsUploadingAvatar(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {agentId ? t('edit.title', { fallback: 'Edit Agent' }) : t('create.title', { fallback: 'Create Agent' })}
          </DialogTitle>
        </DialogHeader>

        {isLoading ? (
          <div className="flex justify-center items-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-6 py-4">
            <div className="flex flex-col items-center gap-4 mb-6">
              <div className="relative group cursor-pointer" onClick={handleAvatarClick}>
                <AgentAvatar
                  url={avatarUrl}
                  name={name || 'New Agent'}
                  size="lg"
                  className="h-16 w-16 transition-opacity group-hover:opacity-80"
                />
                <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/40 rounded-xl">
                  {isUploadingAvatar ? (
                    <Loader2 className="h-5 w-5 animate-spin text-white" />
                  ) : (
                    <Upload className="h-5 w-5 text-white" />
                  )}
                </div>
                <input type="file" ref={fileInputRef} className="hidden" accept="image/*" onChange={handleFileChange} />
              </div>
              <div className="flex flex-wrap justify-center gap-1.5 max-w-[280px]">
                {Object.keys(AGENT_ICON_REGISTRY).map((iconId) => (
                  <button
                    key={iconId}
                    type="button"
                    className={cn(
                      'rounded-lg p-0.5 transition-all hover:scale-110',
                      avatarUrl === `icon:${iconId}`
                        ? 'ring-2 ring-primary ring-offset-1 ring-offset-background'
                        : 'opacity-60 hover:opacity-100',
                    )}
                    onClick={() => setValue('avatar_url', `icon:${iconId}`)}
                  >
                    <AgentIcon iconId={iconId} size="sm" />
                  </button>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                {t('avatar.hint', { fallback: 'Select an icon or click above to upload' })}
              </p>
            </div>

            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name">
                  {t('form.name', { fallback: 'Name' })} <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="name"
                  {...register('name')}
                  placeholder={t('form.namePlaceholder', { fallback: 'e.g. Code Reviewer' })}
                />
                {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">{t('form.description', { fallback: 'Description' })}</Label>
                <Input
                  id="description"
                  {...register('description')}
                  placeholder={t('form.descriptionPlaceholder', {
                    fallback: 'Briefly describe what this agent does',
                  })}
                />
                {errors.description && <p className="text-sm text-destructive">{errors.description.message}</p>}
              </div>

              <div className="space-y-2">
                <Label htmlFor="agent_type" className="flex items-center gap-1.5">
                  <Users size={14} className="text-muted-foreground" />
                  {t('form.agentType', { fallback: 'Agent Type' })}
                </Label>
                <Select value={agentType} onValueChange={(v) => setAgentType(v as AgentType)}>
                  <SelectTrigger id="agent_type" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="individual">
                      <div className="flex flex-col py-0.5">
                        <span>{t('form.agentTypeIndividual', { fallback: 'Individual' })}</span>
                        <span className="text-xs text-muted-foreground">
                          {t('form.agentTypeIndividualDesc', { fallback: 'Standard single agent' })}
                        </span>
                      </div>
                    </SelectItem>
                    <SelectItem value="team">
                      <div className="flex flex-col py-0.5">
                        <span>{t('form.agentTypeTeam', { fallback: 'Team Leader' })}</span>
                        <span className="text-xs text-muted-foreground">
                          {t('form.agentTypeTeamDesc', {
                            fallback: 'Coordinates subagents as team members',
                          })}
                        </span>
                      </div>
                    </SelectItem>
                  </SelectContent>
                </Select>
                {agentType === 'team' && (
                  <p className="text-xs text-muted-foreground mt-1">
                    {t('form.agentTypeTeamHint', {
                      fallback:
                        'Configure team members in the Agent config panel after creation. The leader will automatically coordinate delegated subagents.',
                    })}
                  </p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="system_prompt">{t('form.systemPrompt', { fallback: 'System Prompt' })}</Label>
                <TextareaAutosize
                  id="system_prompt"
                  {...register('system_prompt')}
                  minRows={4}
                  maxRows={12}
                  className="flex w-full rounded-full border border-input bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 resize-none"
                  placeholder={t('form.systemPromptPlaceholder', {
                    fallback: 'You are a helpful assistant...',
                  })}
                />
                {errors.system_prompt && <p className="text-sm text-destructive">{errors.system_prompt.message}</p>}
              </div>

              <CommandBindingsEditor value={commandBindings} onChange={setCommandBindings} />

              {/* Tool Gateway Policy */}
              <div className="space-y-3 rounded-lg border border-border/60 p-4">
                <div className="flex items-center justify-between">
                  <Label className="text-sm font-medium">
                    {t('form.toolGateway.title', { fallback: 'Unified Tool Gateway' })}
                  </Label>
                  <Switch
                    checked={toolGatewayConfig.use_gateway}
                    onCheckedChange={(v) => setToolGatewayConfig({ ...toolGatewayConfig, use_gateway: v })}
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  {t('form.toolGateway.description', {
                    fallback:
                      'Route third-party tool traffic (Search, Image Gen, TTS, Browser) through the unified gateway. Requires BYOK/PAT configuration in Settings for Local/Desktop environments.',
                  })}
                </p>
              </div>

              {/* Session Policy */}
              <div className="space-y-3 rounded-lg border border-border/60 p-4">
                <div className="space-y-2">
                  <Label className="text-sm font-medium">
                    {t('form.browserEngine', { fallback: 'Browser Engine' })}
                  </Label>
                  <Select value={browserEngine} onValueChange={setBrowserEngine}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="chromium_patchright">
                        <div className="flex flex-col py-0.5">
                          <span>{t('form.browserEngineChromium', { fallback: 'Standard (Chromium)' })}</span>
                          <span className="text-xs text-muted-foreground">
                            {t('form.browserEngineChromiumDesc', { fallback: 'Default engine. Fast and lightweight.' })}
                          </span>
                        </div>
                      </SelectItem>
                      <SelectItem value="firefox_camoufox">
                        <div className="flex flex-col py-0.5">
                          <span>{t('form.browserEngineFirefox', { fallback: 'High Stealth (Firefox Camoufox)' })}</span>
                          <span className="text-xs text-muted-foreground">
                            {t('form.browserEngineFirefoxDesc', {
                              fallback: 'Bypasses advanced WAFs (e.g. Cloudflare Turnstile). Slower startup.',
                            })}
                          </span>
                        </div>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2 pt-2">
                  <Label className="text-sm font-medium">
                    {t('form.browserSource', { fallback: 'Browser Source' })}
                  </Label>
                  <Select value={browserSource} onValueChange={setBrowserSource}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="auto">
                        <div className="flex flex-col py-0.5">
                          <span>{t('form.browserSourceAuto', { fallback: 'Auto (System Default)' })}</span>
                          <span className="text-xs text-muted-foreground">
                            {t('form.browserSourceAutoDesc', { fallback: 'Automatically detect the best browser source.' })}
                          </span>
                        </div>
                      </SelectItem>
                      <SelectItem value="extension">
                        <div className="flex flex-col py-0.5">
                          <span>{t('form.browserSourceExtension', { fallback: 'Browser Extension' })}</span>
                          <span className="text-xs text-muted-foreground">
                            {t('form.browserSourceExtensionDesc', { fallback: 'Use your real browser via extension bridge. Preserves your login sessions.' })}
                          </span>
                        </div>
                      </SelectItem>
                      <SelectItem value="launch">
                        <div className="flex flex-col py-0.5">
                          <span>{t('form.browserSourceLaunch', { fallback: 'Launch New Browser' })}</span>
                          <span className="text-xs text-muted-foreground">
                            {t('form.browserSourceLaunchDesc', { fallback: 'Launch a fresh isolated browser instance.' })}
                          </span>
                        </div>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                  {browserSource === 'extension' && (
                    <p className="text-xs text-amber-600 dark:text-amber-400 flex items-center gap-1">
                      <AlertCircle size={12} />
                      {t('form.browserSourceExtensionWarning', { fallback: 'Requires Browser Extension to be connected. The agent will operate in your real browser.' })}
                    </p>
                  )}
                </div>
              </div>

              <div className="space-y-3 rounded-lg border border-border/60 p-4">
                <div className="flex items-center justify-between">
                  <Label className="text-sm font-medium">
                    {t('form.sessionPolicy.title', { fallback: 'Session Policy' })}
                  </Label>
                  <Switch checked={sessionPolicyEnabled} onCheckedChange={setSessionPolicyEnabled} />
                </div>
                <p className="text-xs text-muted-foreground">
                  {t('form.sessionPolicy.description', {
                    fallback: 'Override global session reset strategy for this agent.',
                  })}
                </p>

                {sessionPolicyEnabled && (
                  <div className="space-y-3 pt-2">
                    <div className="space-y-1.5">
                      <Label className="text-xs">{t('form.sessionPolicy.mode', { fallback: 'Reset Mode' })}</Label>
                      <Select
                        value={sessionPolicy.mode}
                        onValueChange={(v) => setSessionPolicy((prev) => ({ ...prev, mode: v as SessionResetMode }))}
                      >
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="persistent">
                            <div className="flex flex-col py-0.5">
                              <span>{t('form.sessionPolicy.modePersistent', { fallback: 'Persistent' })}</span>
                              <span className="text-xs text-muted-foreground">
                                {t('form.sessionPolicy.modePersistentDesc', {
                                  fallback: 'Never reset, single continuous session',
                                })}
                              </span>
                            </div>
                          </SelectItem>
                          <SelectItem value="daily">
                            <div className="flex flex-col py-0.5">
                              <span>{t('form.sessionPolicy.modeDaily', { fallback: 'Daily' })}</span>
                              <span className="text-xs text-muted-foreground">
                                {t('form.sessionPolicy.modeDailyDesc', {
                                  fallback: 'New session at a specific hour each day',
                                })}
                              </span>
                            </div>
                          </SelectItem>
                          <SelectItem value="idle">
                            <div className="flex flex-col py-0.5">
                              <span>{t('form.sessionPolicy.modeIdle', { fallback: 'Idle Timeout' })}</span>
                              <span className="text-xs text-muted-foreground">
                                {t('form.sessionPolicy.modeIdleDesc', {
                                  fallback: 'New session after inactivity threshold',
                                })}
                              </span>
                            </div>
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    {sessionPolicy.mode === 'daily' && (
                      <div className="space-y-1.5">
                        <Label className="text-xs">
                          {t('form.sessionPolicy.dailyResetHour', { fallback: 'Reset Hour (UTC)' })}
                        </Label>
                        <Select
                          value={String(sessionPolicy.daily_reset_hour)}
                          onValueChange={(v) => setSessionPolicy((prev) => ({ ...prev, daily_reset_hour: Number(v) }))}
                        >
                          <SelectTrigger className="w-full">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {Array.from({ length: 24 }, (_, i) => (
                              <SelectItem key={i} value={String(i)}>
                                {String(i).padStart(2, '0')}:00 UTC
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    )}

                    {sessionPolicy.mode === 'idle' && (
                      <div className="space-y-1.5">
                        <Label className="text-xs">
                          {t('form.sessionPolicy.idleMinutes', { fallback: 'Idle Timeout (min)' })}
                        </Label>
                        <Input
                          type="number"
                          min={1}
                          max={10080}
                          value={sessionPolicy.idle_minutes}
                          onChange={(e) =>
                            setSessionPolicy((prev) => ({
                              ...prev,
                              idle_minutes: Math.max(1, Math.min(10080, Number(e.target.value) || 1)),
                            }))
                          }
                        />
                        <p className="text-xs text-muted-foreground">
                          {t('form.sessionPolicy.idleMinutesHint', {
                            fallback: '1 ~ 10080 minutes (7 days max)',
                          })}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t('cancel', { fallback: 'Cancel' })}
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t('save', { fallback: 'Save' })}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
