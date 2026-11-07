'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import {
  Download,
  Star,
  ExternalLink,
  Loader2,
  CheckCircle,
  Globe,
  ArrowUpCircle,
  Trash2,
  Store,
  MessageSquare,
  Cloud,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { resolveSkillDescription } from '@/lib/utils/skillUtils';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import type { DiscoverySearchResult } from '@/services/skill';
import { getWorkBuddyMigrationInfo } from '@/services/skillsMigrationMap';

const SOURCE_ICONS: Record<string, typeof Globe> = {
  prebuilt: Globe,
  github: Globe,
  skills_sh: Globe,
  clawhub: Store,
  lobehub: MessageSquare,
  modelscope: Cloud,
  aliyun: Cloud,
};

const SOURCE_COLORS: Record<string, string> = {
  prebuilt: 'text-accent-warm',
  github: 'text-muted-foreground',
  skills_sh: 'text-primary',
  clawhub: 'text-accent-warm',
  lobehub: 'text-primary',
  modelscope: 'text-primary',
  aliyun: 'text-accent-warm',
};

// ========== Tag Button ==========

export function TagButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'no-brand-elevation px-2.5 py-1 text-xs rounded-lg transition-colors',
        active
          ? 'bg-primary text-primary-foreground'
          : 'bg-muted text-muted-foreground hover:bg-accent border border-border',
      )}
    >
      {children}
    </button>
  );
}

export function TranslatedTag({ tag }: { tag: string }) {
  const tSkills = useTranslations('settings.skills');
  const key = `tagLabels.${tag.toLowerCase()}` as Parameters<typeof tSkills>[0];
  return <>{tSkills.has(key) ? tSkills(key) : tag}</>;
}

// ========== Skill Result Card ==========

interface SkillResultCardProps {
  skill: DiscoverySearchResult;
  isInstalling: boolean;
  isPreviewing: boolean;
  isUninstalling: boolean;
  justInstalled: boolean;
  onInstall: (skill: DiscoverySearchResult) => void;
  onUninstall: (skill: DiscoverySearchResult) => void;
  t: ReturnType<typeof useTranslations>;
}

export const SkillResultCard = memo(
  ({
    skill,
    isInstalling,
    isPreviewing,
    isUninstalling,
    justInstalled,
    onInstall,
    onUninstall,
    t,
  }: SkillResultCardProps) => {
    const SourceIcon = SOURCE_ICONS[skill.source] || Globe;
    const sourceColor =
      SOURCE_COLORS[skill.source] || (skill.source.startsWith('well-known:') ? 'text-primary' : 'text-gray-500');
    const sourceLabel = skill.source.startsWith('well-known:')
      ? skill.source.replace('well-known:', '').replace(/^https?:\/\//, '')
      : t(`source.${skill.source}` as Parameters<typeof t>[0]);
    const isBusy = isInstalling || isPreviewing || isUninstalling;
    const isLocalInstalled = !!skill.installed_version;
    const wbMigrationInfo = getWorkBuddyMigrationInfo(skill.id) || getWorkBuddyMigrationInfo(skill.name);

    return (
      <div
        className={cn('p-4 rounded-lg border bg-card transition-colors', 'hover:border-primary/30 hover:bg-accent/30')}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h4 className="font-medium text-sm truncate">{skill.name}</h4>
              <Badge variant="outline" className={cn('text-xs shrink-0 gap-1', sourceColor)}>
                <SourceIcon className="h-3 w-3" />
                {sourceLabel}
              </Badge>
              {wbMigrationInfo && (
                <Badge
                  variant="secondary"
                  className="text-[10px] px-1.5 py-0 bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20"
                >
                  WB Top 20
                </Badge>
              )}
              {skill.package_type === 'agent_plugin' && (
                <Badge
                  variant="secondary"
                  className="text-[10px] px-1.5 py-0 bg-primary/10 text-primary border-primary/20"
                >
                  Plugin
                </Badge>
              )}
              {skill.upgrade_available && (
                <Badge
                  variant="secondary"
                  className="text-xs shrink-0 gap-1 text-amber-600 dark:text-amber-400 bg-amber-500/10"
                >
                  <ArrowUpCircle className="h-3 w-3" />
                  {t('updateAvailable')}
                </Badge>
              )}
            </div>

            <div className="flex items-center gap-3 text-xs text-muted-foreground mb-2">
              {skill.author && <span>{skill.author}</span>}
              {skill.stars > 0 && (
                <span className="flex items-center gap-0.5">
                  <Star className="h-3 w-3" />
                  {skill.stars}
                </span>
              )}
              {skill.installed_version && (
                <span className="text-accent-warm font-medium">
                  v{skill.installed_version}
                  {skill.upgrade_available && skill.version && ` → v${skill.version}`}
                </span>
              )}
            </div>

            <p className="text-xs text-muted-foreground line-clamp-2">
              {resolveSkillDescription(skill, t('noDescription'))}
            </p>

            {skill.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {skill.tags.slice(0, 3).map((tag) => (
                  <Badge key={tag} variant="secondary" className="text-[10px] px-1.5 py-0">
                    <TranslatedTag tag={tag} />
                  </Badge>
                ))}
              </div>
            )}
          </div>

          <div className="flex flex-col items-end gap-1 shrink-0">
            <Button
              size="sm"
              variant={justInstalled ? 'outline' : skill.upgrade_available ? 'secondary' : 'default'}
              disabled={isBusy || justInstalled}
              onClick={() => onInstall(skill)}
              className="gap-1.5"
            >
              {isPreviewing ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  {t('scanning')}
                </>
              ) : isInstalling ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  {skill.upgrade_available ? t('updating') : t('installing')}
                </>
              ) : justInstalled ? (
                <>
                  <CheckCircle className="h-3.5 w-3.5 text-green-500" />
                  {t('installed')}
                </>
              ) : skill.upgrade_available ? (
                <>
                  <ArrowUpCircle className="h-3.5 w-3.5" />
                  {t('update')}
                </>
              ) : (
                <>
                  <Download className="h-3.5 w-3.5" />
                  {t('install')}
                </>
              )}
            </Button>
            {isLocalInstalled && !skill.upgrade_available && (
              <Button
                size="sm"
                variant="ghost"
                disabled={isBusy}
                onClick={() => onUninstall(skill)}
                className="gap-1.5 text-destructive-text hover:text-destructive-text"
              >
                {isUninstalling ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    {t('uninstalling')}
                  </>
                ) : (
                  <>
                    <Trash2 className="h-3.5 w-3.5" />
                    {t('uninstall')}
                  </>
                )}
              </Button>
            )}
            {skill.readme_url && (
              <a
                href={skill.readme_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-muted-foreground hover:text-primary flex items-center gap-1"
              >
                <ExternalLink className="h-3 w-3" />
                README
              </a>
            )}
          </div>
        </div>
      </div>
    );
  },
);
SkillResultCard.displayName = 'SkillResultCard';
