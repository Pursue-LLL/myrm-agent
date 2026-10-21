'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';

import { IconFolder, IconUsers } from '@/components/features/icons/PremiumIcons';
import { Badge } from '@/components/primitives/badge';
import { ToggleGroup, ToggleGroupItem } from '@/components/primitives/toggle-group';

import { ImportSection, listNames, Note, ResolutionToggle } from './PluginImportParts';
import type { ComponentDecision, PluginAgentPreview, Resolution } from './pluginImportTypes';

function AgentNotes({ item }: { item: PluginAgentPreview }) {
  const t = useTranslations('settings.plugins.import.agents');
  const iterationsCapped =
    item.max_iterations !== null &&
    item.effective_max_iterations !== null &&
    item.effective_max_iterations < item.max_iterations;

  return (
    <>
      {item.withheld_tools.length > 0 && (
        <Note tone="caution">{t('withheldTools', { tools: listNames(item.withheld_tools) })}</Note>
      )}
      {item.unresolved_skills.length > 0 && (
        <Note tone="caution">{t('unresolvedSkills', { names: listNames(item.unresolved_skills) })}</Note>
      )}
      {item.unresolved_connectors.length > 0 && (
        <Note tone="caution">{t('unresolvedConnectors', { names: listNames(item.unresolved_connectors) })}</Note>
      )}
      {item.unresolved_subagents.length > 0 && (
        <Note tone="caution">{t('unresolvedSubagents', { names: listNames(item.unresolved_subagents) })}</Note>
      )}
      {iterationsCapped && (
        <Note>
          {t('iterationsCapped', {
            requested: item.max_iterations ?? 0,
            effective: item.effective_max_iterations ?? 0,
          })}
        </Note>
      )}
      {item.recommended_model && <Note>{t('recommendedModel', { model: item.recommended_model })}</Note>}
      {item.ignored_declarations.length > 0 && (
        <Note>{t('ignoredDeclarations', { names: listNames(item.ignored_declarations) })}</Note>
      )}
    </>
  );
}

function AgentDecision({
  item,
  resolution,
  disabled,
  onResolve,
}: {
  item: PluginAgentPreview;
  resolution: Resolution | undefined;
  disabled: boolean;
  onResolve: (resolution: Resolution) => void;
}) {
  const t = useTranslations('settings.plugins.import');

  if (!item.conflict) {
    const installed = resolution === 'install';
    return (
      <ResolutionToggle
        active={installed}
        label={installed ? t('actions.install') : t('actions.skip')}
        disabled={disabled}
        onClick={() => onResolve(installed ? 'skip' : 'install')}
      />
    );
  }

  // Replacing keeps the same expert id (and its history); a built-in expert is never overwritten.
  return (
    <ToggleGroup
      type="single"
      value={resolution}
      onValueChange={(value) => value && onResolve(value as Resolution)}
      disabled={disabled}
      aria-label={item.name}
      className="gap-0.5 rounded-lg border bg-muted/30 p-0.5"
    >
      <ToggleGroupItem
        value="install"
        className="h-7 px-2.5 text-xs data-[state=on]:bg-background data-[state=on]:shadow-sm"
      >
        {t('actions.importCopy')}
      </ToggleGroupItem>
      {!item.existing_is_built_in && (
        <ToggleGroupItem
          value="replace"
          className="h-7 px-2.5 text-xs data-[state=on]:bg-background data-[state=on]:shadow-sm"
        >
          {t('actions.replace')}
        </ToggleGroupItem>
      )}
      <ToggleGroupItem
        value="skip"
        className="h-7 px-2.5 text-xs data-[state=on]:bg-background data-[state=on]:shadow-sm"
      >
        {t('actions.skip')}
      </ToggleGroupItem>
    </ToggleGroup>
  );
}

function AgentRow({
  item,
  resolution,
  disabled,
  onResolve,
}: {
  item: PluginAgentPreview;
  resolution: Resolution | undefined;
  disabled: boolean;
  onResolve: (resolution: Resolution) => void;
}) {
  const t = useTranslations('settings.plugins.import');

  return (
    <div className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium">{item.name}</p>
          {item.is_entry_agent && (
            <Badge variant="default" className="px-1.5 py-0 text-[10px] font-normal">
              {t('agents.entry')}
            </Badge>
          )}
          {item.is_subagent && !item.is_entry_agent && (
            <Badge variant="secondary" className="px-1.5 py-0 text-[10px] font-normal">
              {t('agents.subagent')}
            </Badge>
          )}
        </div>
        {item.description && <p className="mt-0.5 truncate text-xs text-muted-foreground">{item.description}</p>}
        <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          {item.skill_names.length > 0 && <span>{t('agents.skillsCount', { count: item.skill_names.length })}</span>}
          {item.granted_tools.length > 0 && (
            <span>· {t('agents.toolsCount', { count: item.granted_tools.length })}</span>
          )}
          {item.subagent_names.length > 0 && (
            <span>· {t('agents.subagentsCount', { count: item.subagent_names.length })}</span>
          )}
        </div>
        {item.conflict && (
          <Note tone="caution">{item.existing_is_built_in ? t('agents.conflictBuiltIn') : t('agents.conflict')}</Note>
        )}
        <AgentNotes item={item} />
      </div>
      <div className="shrink-0">
        <AgentDecision item={item} resolution={resolution} disabled={disabled} onResolve={onResolve} />
      </div>
    </div>
  );
}

interface PluginAgentsSectionProps {
  items: PluginAgentPreview[];
  decisions: ComponentDecision[];
  workspaceFileCount: number;
  disabled: boolean;
  onResolve: (virtualId: string, resolution: Resolution) => void;
  onAll: (target: 'install' | 'skip') => void;
}

export const PluginAgentsSection = memo(
  ({ items, decisions, workspaceFileCount, disabled, onResolve, onAll }: PluginAgentsSectionProps) => {
    const t = useTranslations('settings.plugins.import');
    return (
      <>
        {items.length > 0 && (
          <ImportSection
            icon={IconUsers}
            title={t('sections.agents', { count: items.length })}
            onSelectAll={() => onAll('install')}
            onSkipAll={() => onAll('skip')}
          >
            {items.map((item) => (
              <AgentRow
                key={item.virtual_id}
                item={item}
                resolution={decisions.find((d) => d.virtual_id === item.virtual_id)?.resolution}
                disabled={disabled}
                onResolve={(resolution) => onResolve(item.virtual_id, resolution)}
              />
            ))}
          </ImportSection>
        )}
        {workspaceFileCount > 0 && (
          <div className="flex items-center justify-between rounded-xl border bg-muted/20 px-4 py-3">
            <div className="flex items-center gap-2 text-sm">
              <IconFolder className="h-4 w-4 text-primary" />
              <span className="font-medium">{t('sections.workspaceFiles', { count: workspaceFileCount })}</span>
            </div>
            <Badge variant="outline" className="text-xs">
              {t('agents.templateFiles', { count: workspaceFileCount })}
            </Badge>
          </div>
        )}
      </>
    );
  },
);
PluginAgentsSection.displayName = 'PluginAgentsSection';
