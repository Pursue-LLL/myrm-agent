'use client';

import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { toast } from '@/hooks/shared/useToast';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/primitives/select';
import {
  getExtensionClipAgentConfig,
  updateExtensionClipAgentConfig,
} from '@/services/extension';
import { listAgents, type AgentListItem } from '@/services/agent';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';

const ExtensionClipAgentField = memo(() => {
  const t = useTranslations('settings');
  const locale = useLocale();
  const [agents, setAgents] = useState<AgentListItem[]>([]);
  const [clipAgentId, setClipAgentId] = useState<string | null>(null);
  const [clipAgentSaving, setClipAgentSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const loadClipAgentConfig = async () => {
      try {
        const [agentResponse, clipConfig] = await Promise.all([
          listAgents(1, 100),
          getExtensionClipAgentConfig(),
        ]);
        if (cancelled) return;
        setAgents(agentResponse.items);
        setClipAgentId(clipConfig.agent_id);
      } catch {
        if (!cancelled) {
          setAgents([]);
        }
      }
    };
    void loadClipAgentConfig();
    return () => {
      cancelled = true;
    };
  }, []);

  const clipAgentOptions = useMemo(() => {
    const options = agents.map((agent) => ({
      id: agent.id,
      label: getBuiltinAgentName(agent.id, agent.name, locale),
    }));
    if (clipAgentId && !options.some((option) => option.id === clipAgentId)) {
      options.unshift({ id: clipAgentId, label: clipAgentId });
    }
    return options;
  }, [agents, clipAgentId, locale]);

  const handleClipAgentChange = useCallback(
    async (value: string) => {
      const nextAgentId = value === 'default' ? null : value;
      setClipAgentSaving(true);
      try {
        const webUiOrigin = typeof window !== 'undefined' ? window.location.origin : null;
        const result = await updateExtensionClipAgentConfig(nextAgentId, webUiOrigin);
        setClipAgentId(result.agent_id);
        toast({ title: t('extension.clipAgentSaved'), variant: 'default' });
      } catch {
        toast({ title: t('extension.clipAgentSaveFailed'), variant: 'destructive' });
      } finally {
        setClipAgentSaving(false);
      }
    },
    [t],
  );

  return (
    <div className="p-4 rounded-lg border border-border/50 bg-background/50 space-y-3">
      <div className="space-y-1">
        <h4 className="text-sm font-medium">{t('extension.clipAgentLabel')}</h4>
        <p className="text-xs text-muted-foreground">{t('extension.clipAgentHint')}</p>
      </div>
      <Select
        value={clipAgentId ?? 'default'}
        onValueChange={handleClipAgentChange}
        disabled={clipAgentSaving}
      >
        <SelectTrigger className="w-full sm:max-w-md">
          <SelectValue placeholder={t('extension.clipAgentDefault')} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="default">{t('extension.clipAgentDefault')}</SelectItem>
          {clipAgentOptions.map((agent) => (
            <SelectItem key={agent.id} value={agent.id}>
              {agent.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
});

ExtensionClipAgentField.displayName = 'ExtensionClipAgentField';

export default ExtensionClipAgentField;
