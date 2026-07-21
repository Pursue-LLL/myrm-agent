'use client';

/**
 * [INPUT]
 * @/services/cron::updateCronJob (POS: Frontend Cron API client)
 * @/store/chat/types/builtinTools::BUILTIN_TOOL_IDS (POS: Builtin tool ID registry)
 * ./CronDeliveryEditors::EditorProps (POS: Cron per-job editor shared props)
 *
 * [OUTPUT]
 * CapabilityEditor: Cron agent execution policy editor (required_capabilities + tools_allowed presets).
 *
 * [POS]
 * CronRunHistory per-job surface. Presets mirror server blueprints.py _CAP_* / _TOOLS_* SSOT.
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Shield,
  Globe,
  Download,
  Terminal,
  FileInput,
  FileOutput,
  Plug,
  Code,
  Wrench,
} from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { ToggleGroup, ToggleGroupItem } from '@/components/primitives/toggle-group';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import { toast } from 'sonner';
import { updateCronJob } from '@/services/cron';
import { BUILTIN_TOOL_IDS, type BuiltinToolId } from '@/store/chat/types/builtinTools';
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

/** SSOT: keep aligned with server `blueprints.py` `_CAP_*` / `_TOOLS_*`. */
const BLUEPRINT_EXECUTION_POLICY = {
  web: {
    caps: ['web_search_tool', 'net_fetch'],
    capsSorted: ['net_fetch', 'web_search_tool'],
    tools: ['web_search'] as BuiltinToolId[],
    toolsSorted: ['web_search'],
  },
  research: {
    caps: ['web_search_tool', 'net_fetch', 'file_read'],
    capsSorted: ['file_read', 'net_fetch', 'web_search_tool'],
    tools: ['web_search', 'file_ops'] as BuiltinToolId[],
    toolsSorted: ['file_ops', 'web_search'],
  },
  devops: {
    caps: ['shell_exec', 'file_read', 'file_write', 'code_interpreter_tool'],
    capsSorted: ['code_interpreter_tool', 'file_read', 'file_write', 'shell_exec'],
    tools: ['web_search', 'file_ops', 'code_execute'] as BuiltinToolId[],
    toolsSorted: ['code_execute', 'file_ops', 'web_search'],
  },
} as const;

const CAPABILITY_PRESETS = [
  {
    key: 'research',
    caps: [...BLUEPRINT_EXECUTION_POLICY.research.caps],
    sorted: [...BLUEPRINT_EXECUTION_POLICY.research.capsSorted],
    tools: [...BLUEPRINT_EXECUTION_POLICY.research.tools],
    toolsSorted: [...BLUEPRINT_EXECUTION_POLICY.research.toolsSorted],
  },
  {
    key: 'devops',
    caps: [...BLUEPRINT_EXECUTION_POLICY.devops.caps],
    sorted: [...BLUEPRINT_EXECUTION_POLICY.devops.capsSorted],
    tools: [...BLUEPRINT_EXECUTION_POLICY.devops.tools],
    toolsSorted: [...BLUEPRINT_EXECUTION_POLICY.devops.toolsSorted],
  },
  { key: 'full', caps: [] as string[], sorted: [] as string[], tools: [] as BuiltinToolId[], toolsSorted: [] as string[] },
] as const;

const CRON_BUILTIN_TOOL_IDS = BUILTIN_TOOL_IDS.filter((id) => id !== 'cron') as BuiltinToolId[];

/** Baseline tools are cron-restrictable even though they are hidden from agent settings toggles. */
const CRON_TOOL_IDS = ['file_ops', 'code_execute', ...CRON_BUILTIN_TOOL_IDS] as const;

const TOOL_PRESETS = [
  {
    key: 'webOnly',
    caps: [...BLUEPRINT_EXECUTION_POLICY.web.caps],
    tools: [...BLUEPRINT_EXECUTION_POLICY.web.tools],
    sorted: [...BLUEPRINT_EXECUTION_POLICY.web.toolsSorted],
  },
  {
    key: 'research',
    caps: [...BLUEPRINT_EXECUTION_POLICY.research.caps],
    tools: [...BLUEPRINT_EXECUTION_POLICY.research.tools],
    sorted: [...BLUEPRINT_EXECUTION_POLICY.research.toolsSorted],
  },
  {
    key: 'devops',
    caps: [...BLUEPRINT_EXECUTION_POLICY.devops.caps],
    tools: [...BLUEPRINT_EXECUTION_POLICY.devops.tools],
    sorted: [...BLUEPRINT_EXECUTION_POLICY.devops.toolsSorted],
  },
  { key: 'full', caps: [] as string[], tools: [] as BuiltinToolId[], sorted: [] as string[] },
] as const;

function sortedEqual(a: readonly string[], b: readonly string[]): boolean {
  const left = [...a].sort();
  const right = [...b].sort();
  return left.length === right.length && left.every((v, i) => v === right[i]);
}

export function CapabilityEditor({ job, onUpdated }: EditorProps) {
  const t = useTranslations('cron');
  const tPanel = useTranslations('agent.configPanel');

  const serverCaps = job.required_capabilities ?? [];
  const serverTools = job.tools_allowed ?? [];
  const [localCaps, setLocalCaps] = useState<string[]>(serverCaps);
  const [localTools, setLocalTools] = useState<string[]>(serverTools);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLocalCaps(job.required_capabilities ?? []);
    setLocalTools(job.tools_allowed ?? []);
  }, [job.required_capabilities, job.tools_allowed]);

  const capsDirty = useMemo(() => !sortedEqual(localCaps, serverCaps), [localCaps, serverCaps]);
  const toolsDirty = useMemo(() => !sortedEqual(localTools, serverTools), [localTools, serverTools]);
  const dirty = capsDirty || toolsDirty;

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateCronJob(job.id, {
        required_capabilities: localCaps,
        tools_allowed: localTools,
      });
      onUpdated();
      toast.success(t('executionPolicyUpdated'));
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-lg border bg-card px-3 py-2.5 space-y-4">
      <div className="space-y-2">
        <div className="flex items-center gap-1.5">
          <Shield className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">{t('capabilitiesLabel')}</span>
        </div>
        <p className="text-[11px] text-muted-foreground">{t('capabilitiesDesc')}</p>
        <div className="flex items-center gap-1.5 flex-wrap">
          {CAPABILITY_PRESETS.map(({ key, caps, sorted, tools }) => {
            const isActive = sortedEqual(sorted, localCaps);
            return (
              <button
                key={key}
                type="button"
                disabled={saving}
                onClick={() => {
                  setLocalCaps([...caps]);
                  setLocalTools([...tools]);
                }}
                className={`text-[11px] px-2 py-0.5 rounded-full border transition-colors ${
                  isActive
                    ? 'bg-primary/10 text-primary border-primary/40'
                    : 'bg-muted/50 text-muted-foreground border-border hover:bg-muted'
                }`}
              >
                {t(`capPreset.${key}`)}
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
      </div>

      <div className="space-y-2 border-t border-border/60 pt-3">
        <div className="flex items-center gap-1.5">
          <Wrench className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">{t('toolsAllowedLabel')}</span>
        </div>
        <p className="text-[11px] text-muted-foreground">{t('toolsAllowedDesc')}</p>
        <div className="flex items-center gap-1.5 flex-wrap">
          {TOOL_PRESETS.map(({ key, caps, tools, sorted }) => {
            const isActive =
              sortedEqual(sorted, localTools) && sortedEqual(caps, localCaps);
            return (
              <button
                key={key}
                type="button"
                disabled={saving}
                onClick={() => {
                  setLocalTools([...tools]);
                  setLocalCaps([...caps]);
                }}
                className={`text-[11px] px-2 py-0.5 rounded-full border transition-colors ${
                  isActive
                    ? 'bg-primary/10 text-primary border-primary/40'
                    : 'bg-muted/50 text-muted-foreground border-border hover:bg-muted'
                }`}
              >
                {t(`toolPreset.${key}`)}
              </button>
            );
          })}
        </div>
        <ToggleGroup
          type="multiple"
          value={localTools}
          onValueChange={setLocalTools}
          className="flex-wrap justify-start"
          size="sm"
        >
          {CRON_TOOL_IDS.map((toolId) => (
            <ToggleGroupItem
              key={toolId}
              value={toolId}
              disabled={saving}
              className="gap-1 text-xs h-7 px-2.5 rounded-full border border-border bg-muted/50 data-[state=on]:bg-primary/10 data-[state=on]:text-primary data-[state=on]:border-primary/40"
            >
              {tPanel(`builtinToolNames.${toolId}`)}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        {localTools.length === 0 && (
          <p className="text-[11px] text-muted-foreground/70 italic">{t('toolsAllowedAllHint')}</p>
        )}
      </div>

      {dirty && (
        <Button size="sm" className="h-7 text-xs" onClick={handleSave} disabled={saving}>
          {t('save')}
        </Button>
      )}
    </div>
  );
}
