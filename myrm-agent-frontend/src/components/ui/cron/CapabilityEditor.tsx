'use client';

import { useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Shield, Globe, Download, Terminal, FileInput, FileOutput, Plug, Code } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { toast } from 'sonner';
import { updateCronJob } from '@/services/cron';
import type { EditorProps } from './CronDeliveryEditors';

const CAPABILITY_DEFS = [
  { id: 'web_search_tool', icon: Globe },
  { id: 'net_fetch', icon: Download },
  { id: 'shell_exec', icon: Terminal },
  { id: 'file_read', icon: FileInput },
  { id: 'file_write', icon: FileOutput },
  { id: 'mcp_invoke', icon: Plug },
  { id: 'code_interpreter_tool', icon: Code },
] as const;

const CAPABILITY_PRESETS = [
  {
    key: 'research',
    caps: ['web_search_tool', 'net_fetch', 'file_read'],
    sorted: ['file_read', 'net_fetch', 'web_search_tool'],
  },
  {
    key: 'devops',
    caps: ['shell_exec', 'file_read', 'file_write'],
    sorted: ['file_read', 'file_write', 'shell_exec'],
  },
  { key: 'full', caps: [] as string[], sorted: [] as string[] },
] as const;

export function CapabilityEditor({ job, onUpdated }: EditorProps) {
  const t = useTranslations('cron');
  const serverCaps = job.required_capabilities ?? [];
  const [localCaps, setLocalCaps] = useState<string[]>(serverCaps);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLocalCaps(job.required_capabilities ?? []);
  }, [job.required_capabilities]);

  const sortedLocal = useMemo(() => [...localCaps].sort(), [localCaps]);

  const dirty = useMemo(() => {
    const b = [...serverCaps].sort();
    return sortedLocal.length !== b.length || sortedLocal.some((v, i) => v !== b[i]);
  }, [sortedLocal, serverCaps]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateCronJob(job.id, { required_capabilities: localCaps });
      onUpdated();
      toast.success(localCaps.length > 0 ? t('capabilitiesUpdated') : t('capabilitiesCleared'));
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-lg border bg-card px-3 py-2.5 space-y-2">
      <div className="flex items-center gap-1.5">
        <Shield className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-xs font-medium text-muted-foreground">{t('capabilitiesLabel')}</span>
      </div>
      <p className="text-[11px] text-muted-foreground">{t('capabilitiesDesc')}</p>
      <div className="flex items-center gap-1.5 flex-wrap">
        {CAPABILITY_PRESETS.map(({ key, caps, sorted }) => {
          const isActive = sorted.length === sortedLocal.length && sorted.every((v, i) => v === sortedLocal[i]);
          return (
            <button
              key={key}
              type="button"
              disabled={saving}
              onClick={() => setLocalCaps([...caps])}
              className={`text-[11px] px-2 py-0.5 rounded-full border transition-colors ${
                isActive
                  ? 'bg-primary/10 text-primary border-primary/40'
                  : 'bg-muted/50 text-muted-foreground border-border hover:bg-muted'
              }`}
            >
              {t(`preset.${key}`)}
            </button>
          );
        })}
      </div>
      <TooltipProvider delayDuration={300}>
        <ToggleGroup
          type="multiple"
          value={localCaps}
          onValueChange={setLocalCaps}
          className="flex-wrap justify-start"
          size="sm"
        >
          {CAPABILITY_DEFS.map(({ id, icon: Icon }) => (
            <Tooltip key={id}>
              <TooltipTrigger asChild>
                <ToggleGroupItem
                  value={id}
                  disabled={saving}
                  className="gap-1 text-xs h-7 px-2.5 rounded-full border border-border bg-muted/50 data-[state=on]:bg-primary/10 data-[state=on]:text-primary data-[state=on]:border-primary/40"
                >
                  <Icon className="h-3 w-3" />
                  {t(`capability.${id}`)}
                </ToggleGroupItem>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-[200px]">
                {t(`capabilityDesc.${id}`)}
              </TooltipContent>
            </Tooltip>
          ))}
        </ToggleGroup>
      </TooltipProvider>
      {localCaps.length === 0 && (
        <p className="text-[11px] text-muted-foreground/70 italic">{t('capabilitiesAllHint')}</p>
      )}
      {dirty && (
        <Button size="sm" className="h-7 text-xs" onClick={handleSave} disabled={saving}>
          {t('save')}
        </Button>
      )}
    </div>
  );
}
