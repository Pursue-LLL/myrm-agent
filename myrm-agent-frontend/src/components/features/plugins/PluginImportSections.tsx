'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';

import { IconAlertTriangle, IconShieldCheck, IconTerminal } from '@/components/features/icons/PremiumIcons';
import { Badge } from '@/components/primitives/badge';
import { cn } from '@/lib/utils/classnameUtils';

import { ImportSection, Note, ResolutionToggle } from './PluginImportParts';
import {
  isServerBlocked,
  isSkillBlocked,
  type ComponentDecision,
  type PluginDiagnostic,
  type PluginServerPreview,
  type PluginSkillPreview,
  type Resolution,
} from './pluginImportTypes';

export function getCapabilityTierBadgeStyle(tier: string): string {
  switch (tier) {
    case 'destructive':
      return 'border-destructive/40 text-destructive bg-destructive/10';
    case 'shell_exec':
      return 'border-amber-500/40 text-amber-600 dark:text-amber-400 bg-amber-500/10';
    case 'network':
    case 'fs_write':
      return 'border-blue-500/40 text-blue-600 dark:text-blue-400 bg-blue-500/10';
    case 'fs_read':
      return 'border-muted-foreground/30 text-muted-foreground bg-muted/20';
    case 'read_only':
    default:
      return 'border-emerald-500/40 text-emerald-600 dark:text-emerald-400 bg-emerald-500/10';
  }
}

interface SectionProps<TPreview> {
  items: TPreview[];
  decisions: ComponentDecision[];
  disabled: boolean;
  onResolve: (virtualId: string, resolution: Resolution) => void;
  onAll: (target: 'install' | 'skip') => void;
}

function SkillRow({
  item,
  resolution,
  disabled,
  onResolve,
}: {
  item: PluginSkillPreview;
  resolution: Resolution | undefined;
  disabled: boolean;
  onResolve: (resolution: Resolution) => void;
}) {
  const t = useTranslations('settings.plugins.import');
  const blocked = isSkillBlocked(item);
  const active = resolution === 'install' || resolution === 'replace';
  // A same-name skill is upgraded in place, never installed twice.
  const activeResolution: Resolution = item.conflict ? 'replace' : 'install';
  const activeLabel = item.conflict ? t('actions.replace') : t('actions.install');

  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3">
      <div className="min-w-0">
        <p className="text-sm font-medium">{item.name}</p>
        {item.description && !blocked && <p className="truncate text-xs text-muted-foreground">{item.description}</p>}
        {item.oversized_content && <Note tone="danger">{t('security.oversized')}</Note>}
        {!item.oversized_content && item.blocked_reason === 'skills_not_supported' && (
          <Note tone="danger">{t('security.skillsNotSupported')}</Note>
        )}
        {!item.oversized_content && !item.blocked_reason && item.security_issues.length > 0 && (
          <Note tone="danger">{t('security.blocked', { count: item.security_issues.length })}</Note>
        )}
        {item.conflict && !blocked && (
          <>
            <Note tone="caution">{t('security.conflict')}</Note>
            {item.existing_version && <Note>{t('skills.installedVersion', { version: item.existing_version })}</Note>}
          </>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {!blocked && (
          <>
            <Badge variant="outline" className="text-[10px]">
              {item.file_count} {t('sections.files')}
            </Badge>
            <ResolutionToggle
              active={active}
              label={active ? activeLabel : t('actions.skip')}
              disabled={disabled}
              onClick={() => onResolve(active ? 'skip' : activeResolution)}
            />
          </>
        )}
      </div>
    </div>
  );
}

export const PluginSkillsSection = memo(
  ({ items, decisions, disabled, onResolve, onAll }: SectionProps<PluginSkillPreview>) => {
    const t = useTranslations('settings.plugins.import');
    return (
      <ImportSection
        icon={IconShieldCheck}
        title={t('sections.skills', { count: items.length })}
        onSelectAll={() => onAll('install')}
        onSkipAll={() => onAll('skip')}
      >
        {items.map((item) => (
          <SkillRow
            key={item.virtual_id}
            item={item}
            resolution={decisions.find((d) => d.virtual_id === item.virtual_id)?.resolution}
            disabled={disabled}
            onResolve={(resolution) => onResolve(item.virtual_id, resolution)}
          />
        ))}
      </ImportSection>
    );
  },
);
PluginSkillsSection.displayName = 'PluginSkillsSection';

function ServerRow({
  item,
  resolution,
  disabled,
  undeclaredPrivilege,
  onResolve,
}: {
  item: PluginServerPreview;
  resolution: Resolution | undefined;
  disabled: boolean;
  undeclaredPrivilege: boolean;
  onResolve: (resolution: Resolution) => void;
}) {
  const t = useTranslations('settings.plugins.import');
  const blocked = isServerBlocked(item);
  const installed = resolution === 'install';
  const missingFile = item.missing_artifact || item.missing_artifacts[0] || '';

  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3">
      <div className="min-w-0">
        <p className="text-sm font-medium">{item.name}</p>
        <p className="truncate text-xs text-muted-foreground">
          {t(`serverType.${item.type === 'stdio' ? 'local' : 'remote'}`)}
          {item.command ? ` · ${item.command}` : ''}
          {item.url ? ` · ${item.url}` : ''}
          {item.has_placeholders ? ` · ${t('sections.placeholder')}` : ''}
        </p>
        {item.capabilities.length > 0 && (
          <div className="mt-1 flex flex-wrap items-center gap-1">
            {item.capabilities.map((cap) => (
              <Badge
                key={cap}
                variant="outline"
                className={cn('px-1 py-0 text-[10px] font-normal', getCapabilityTierBadgeStyle(cap))}
              >
                {t(`capabilities.${cap}` as Parameters<typeof t>[0])}
              </Badge>
            ))}
          </div>
        )}
        {item.blocked_reason === 'stdio_not_allowed' && <Note tone="danger">{t('security.stdioNotAllowed')}</Note>}
        {!item.blocked_reason && blocked && (
          <Note tone="danger">{t('security.missingArtifact', { file: missingFile })}</Note>
        )}
        {undeclaredPrivilege && (
          <p className="mt-1 flex items-center gap-1 text-xs font-medium text-amber-600 dark:text-amber-400">
            <IconAlertTriangle className="inline h-3.5 w-3.5 shrink-0" />
            {t('capabilities.undeclaredWarning')}
          </p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {item.env_key_count > 0 && (
          <Badge variant="outline" className="text-[10px]">
            {t('sections.envCount', { count: item.env_key_count })}
          </Badge>
        )}
        <ResolutionToggle
          active={installed}
          label={installed ? t('actions.install') : t('actions.skip')}
          disabled={disabled || blocked}
          onClick={() => onResolve(installed ? 'skip' : 'install')}
        />
      </div>
    </div>
  );
}

export const PluginServersSection = memo(
  ({
    items,
    decisions,
    diagnostics,
    disabled,
    onResolve,
    onAll,
  }: SectionProps<PluginServerPreview> & { diagnostics: PluginDiagnostic[] }) => {
    const t = useTranslations('settings.plugins.import');
    return (
      <ImportSection
        icon={IconTerminal}
        title={t('sections.servers', { count: items.length })}
        onSelectAll={() => onAll('install')}
        onSkipAll={() => onAll('skip')}
      >
        {items.map((item) => (
          <ServerRow
            key={item.virtual_id}
            item={item}
            resolution={decisions.find((d) => d.virtual_id === item.virtual_id)?.resolution}
            disabled={disabled}
            undeclaredPrivilege={diagnostics.some(
              (d) => d.code === 'capability_undeclared_privilege' && d.component === `mcp:${item.name}`,
            )}
            onResolve={(resolution) => onResolve(item.virtual_id, resolution)}
          />
        ))}
      </ImportSection>
    );
  },
);
PluginServersSection.displayName = 'PluginServersSection';
