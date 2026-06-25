'use client';

import { memo, useCallback, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import {
  MoreHorizontal,
  Trash2,
  Info,
  FolderOpen,
  AlertTriangle,
  ShieldCheck,
  ShieldAlert,
  ShieldX,
  Shield,
  Clock,
  Pin,
  PinOff,
  Archive,
  RotateCcw,
  Settings2,
  ArrowUpCircle,
  Undo2,
  Download,
} from 'lucide-react';
import { getCategoryIcon, getCategoryColor } from './skillCategories';
import { cn } from '@/lib/utils/classnameUtils';
import { Switch } from '@/components/primitives/switch';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/primitives/dropdown-menu';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import type { Skill, SecurityScanSummary, SkillLifecycleAction } from '@/store/skill/types';
import Link from 'next/link';
import {
  getSkillUnavailableDisplayMessage,
  isGoogleWorkspaceOAuthUnavailable,
  SETTINGS_GOOGLE_OAUTH_PATH,
} from '@/lib/skills/integrationOAuthDisplay';

function getSecurityBadgeProps(security: SecurityScanSummary): {
  icon: React.ElementType;
  color: string;
  label: string;
} {
  const { score } = security;
  if (score >= 80)
    return {
      icon: ShieldCheck,
      color: 'text-green-600 dark:text-green-400',
      label: `${score}`,
    };
  if (score >= 50)
    return {
      icon: Shield,
      color: 'text-yellow-600 dark:text-yellow-400',
      label: `${score}`,
    };
  if (score >= 25)
    return {
      icon: ShieldAlert,
      color: 'text-orange-600 dark:text-orange-400',
      label: `${score}`,
    };
  return {
    icon: ShieldX,
    color: 'text-red-600 dark:text-red-400',
    label: `${score}`,
  };
}

type SkillStatus = 'ready' | 'needs-setup' | 'disabled';

function getSkillStatus(skill: Skill, isEnabled: boolean): SkillStatus {
  if (!isEnabled) return 'disabled';
  if (!skill.available) return 'needs-setup';
  return 'ready';
}

const statusDotColors: Record<SkillStatus, string> = {
  ready: 'bg-green-500',
  'needs-setup': 'bg-amber-500',
  disabled: 'bg-gray-400',
};

interface SkillCardProps {
  skill: Skill;
  isEnabled: boolean;
  showDeleteButton?: boolean;
  onToggle?: (skillId: string) => void;
  onViewDetails?: (skill: Skill) => void;
  onDelete?: (skill: Skill) => void;
  onLifecycleAction?: (skill: Skill, action: SkillLifecycleAction) => void;
  onManageInstances?: (skillName: string) => void;
  onExport?: (skill: Skill) => void;
}

const SkillCard = memo(
  ({
    skill,
    isEnabled,
    showDeleteButton = false,
    onToggle,
    onViewDetails,
    onDelete,
    onLifecycleAction,
    onManageInstances,
    onExport,
  }: SkillCardProps) => {
    const t = useTranslations('settings.skills');
    const status = useMemo(() => getSkillStatus(skill, isEnabled), [skill, isEnabled]);

    const category = skill.category || 'other';
    const CategoryIcon = getCategoryIcon(category);
    const categoryColor = getCategoryColor(category);

    const handleToggle = useCallback(() => {
      onToggle?.(skill.id);
    }, [onToggle, skill.id]);

    const handleViewDetails = useCallback(() => {
      onViewDetails?.(skill);
    }, [onViewDetails, skill]);

    const handleDelete = useCallback(() => {
      onDelete?.(skill);
    }, [onDelete, skill]);

    const lifecycleStatus = skill.usage_stats?.lifecycle_status ?? 'active';
    const isPinned = skill.usage_stats?.pinned ?? false;
    const isStale = lifecycleStatus === 'stale';
    const isArchived = lifecycleStatus === 'archived';
    const isQuarantined = skill.is_active === false;

    const handleLifecycleAction = useCallback(
      (action: SkillLifecycleAction) => {
        onLifecycleAction?.(skill, action);
      },
      [onLifecycleAction, skill],
    );

    const handleExport = useCallback(() => {
      onExport?.(skill);
    }, [onExport, skill]);

    return (
      <div
        className={cn(
          'group relative rounded-xl border bg-card p-4 transition-all duration-200',
          'hover:shadow-md hover:border-primary/30 cursor-pointer',
          isEnabled && !isStale && !isArchived && !isQuarantined && 'border-primary/50 bg-primary/5',
          !skill.available && isEnabled && 'border-amber-400/50 bg-amber-50/50 dark:bg-amber-950/20',
          isStale && 'opacity-70 border-dashed border-amber-400/50',
          isArchived && 'opacity-50 border-dashed border-muted-foreground/30',
          isQuarantined && 'opacity-60 border-destructive/50 bg-destructive/5',
        )}
        onClick={handleViewDetails}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0 flex-1">
            <div className="relative flex-shrink-0">
              <div className={cn('w-10 h-10 rounded-lg flex items-center justify-center', categoryColor)}>
                <CategoryIcon size={20} />
              </div>
              <span
                className={cn(
                  'absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full ring-2 ring-card',
                  statusDotColors[status],
                )}
              />
            </div>

            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <h3 className="font-medium text-foreground truncate">{skill.name}</h3>
                {isPinned && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Pin size={12} className="text-blue-500 shrink-0" />
                    </TooltipTrigger>
                    <TooltipContent>{t('card.pinned')}</TooltipContent>
                  </Tooltip>
                )}
                {isStale && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Badge
                        variant="outline"
                        className="text-xs px-1.5 py-0 border-amber-400 text-amber-600 dark:text-amber-400 cursor-help"
                      >
                        {t('card.stale')}
                      </Badge>
                    </TooltipTrigger>
                    <TooltipContent>
                      {skill.usage_stats?.last_used_at
                        ? t('card.staleReason', { date: new Date(skill.usage_stats.last_used_at).toLocaleDateString() })
                        : t('card.staleReasonNeverUsed')}
                    </TooltipContent>
                  </Tooltip>
                )}
                {isQuarantined && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Badge
                        variant="outline"
                        className="text-xs px-1.5 py-0 border-destructive text-destructive cursor-help"
                      >
                        Quarantined
                      </Badge>
                    </TooltipTrigger>
                    <TooltipContent>
                      This skill has been quarantined due to consecutive errors. It will not be loaded by the agent.
                    </TooltipContent>
                  </Tooltip>
                )}
                {skill.has_upstream_update && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Badge
                        variant="outline"
                        className="text-xs px-1.5 py-0 border-blue-400 bg-blue-50 dark:bg-blue-950/30 text-blue-600 dark:text-blue-400 cursor-help"
                      >
                        {t('card.updateAvailable')}
                      </Badge>
                    </TooltipTrigger>
                    <TooltipContent>{t('card.updateAvailableReason')}</TooltipContent>
                  </Tooltip>
                )}
                {isArchived && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Badge
                        variant="outline"
                        className="text-xs px-1.5 py-0 border-muted-foreground/40 text-muted-foreground cursor-help"
                      >
                        {t('card.archived')}
                      </Badge>
                    </TooltipTrigger>
                    <TooltipContent>{t('card.archivedReason')}</TooltipContent>
                  </Tooltip>
                )}
                {skill.security && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span
                        className={cn(
                          'flex items-center gap-0.5 shrink-0',
                          getSecurityBadgeProps(skill.security).color,
                        )}
                      >
                        {(() => {
                          const { icon: SecurityIcon, label } = getSecurityBadgeProps(skill.security!);
                          return (
                            <>
                              <SecurityIcon size={14} />
                              <span className="text-xs font-medium">{label}</span>
                            </>
                          );
                        })()}
                      </span>
                    </TooltipTrigger>
                    <TooltipContent>
                      {t('card.securityScore', { score: skill.security.score })}
                      {skill.security.total_findings > 0 &&
                        ` · ${t('card.findings', { count: skill.security.total_findings })}`}
                    </TooltipContent>
                  </Tooltip>
                )}
                {skill.author && <span className="text-xs text-muted-foreground shrink-0">by {skill.author}</span>}
              </div>
              <p className="text-sm text-muted-foreground line-clamp-2 mt-0.5">{skill.description}</p>
              {skill.usage_stats && (
                <div className="flex items-center gap-1 mt-1 text-[11px] text-muted-foreground/80">
                  <Clock size={12} />
                  <span>
                    {skill.usage_stats.call_count > 0
                      ? t('card.usageStats', { count: skill.usage_stats.call_count })
                      : t('card.neverUsed')}
                  </span>
                </div>
              )}
              {!skill.available && (skill.unavailable_reason || isGoogleWorkspaceOAuthUnavailable(skill)) && (
                <div className="flex flex-col gap-1 mt-1 text-xs text-amber-600 dark:text-amber-400 sm:flex-row sm:items-center sm:gap-2">
                  <div className="flex items-center gap-1 min-w-0">
                    <AlertTriangle size={12} className="shrink-0" />
                    <span className="truncate">{getSkillUnavailableDisplayMessage(skill, t)}</span>
                  </div>
                  {isGoogleWorkspaceOAuthUnavailable(skill) && (
                    <Link
                      href={SETTINGS_GOOGLE_OAUTH_PATH}
                      className="shrink-0 text-xs font-medium underline underline-offset-2 hover:text-amber-700 dark:hover:text-amber-300"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {t('card.integrationOAuth.googleWorkspace.connectInSettings')}
                    </Link>
                  )}
                </div>
              )}
              {skill.required_permissions && skill.required_permissions.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {skill.required_permissions.map((perm) => (
                    <Badge key={perm} variant="outline" className="text-xs px-1.5 py-0.5 font-normal">
                      {perm.replace(/_/g, ' ')}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
            {!skill.available && isEnabled ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <div>
                    <Switch
                      checked={isEnabled}
                      onCheckedChange={handleToggle}
                      className="data-[state=checked]:bg-amber-500"
                    />
                  </div>
                </TooltipTrigger>
                <TooltipContent>{t('card.needsSetup')}</TooltipContent>
              </Tooltip>
            ) : (
              <Switch checked={isEnabled} onCheckedChange={handleToggle} />
            )}

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <MoreHorizontal size={16} />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={handleViewDetails}>
                  <Info size={16} className="mr-2" />
                  {t('card.details')}
                </DropdownMenuItem>
                {onExport && (
                  <DropdownMenuItem onClick={handleExport}>
                    <Download size={16} className="mr-2" />
                    {t('card.export')}
                  </DropdownMenuItem>
                )}
                {onManageInstances && (
                  <DropdownMenuItem onClick={() => onManageInstances(skill.name)}>
                    <Settings2 size={16} className="mr-2" />
                    {t('card.manageInstances')}
                  </DropdownMenuItem>
                )}
                {onLifecycleAction && (
                  <>
                    {isPinned ? (
                      <DropdownMenuItem onClick={() => handleLifecycleAction('unpin')}>
                        <PinOff size={16} className="mr-2" />
                        {t('card.unpin')}
                      </DropdownMenuItem>
                    ) : (
                      <DropdownMenuItem onClick={() => handleLifecycleAction('pin')}>
                        <Pin size={16} className="mr-2" />
                        {t('card.pin')}
                      </DropdownMenuItem>
                    )}
                    {(isStale || isArchived) && (
                      <DropdownMenuItem onClick={() => handleLifecycleAction('restore')}>
                        <RotateCcw size={16} className="mr-2" />
                        {t('card.restore')}
                      </DropdownMenuItem>
                    )}
                    {!isArchived && !isPinned && (
                      <DropdownMenuItem onClick={() => handleLifecycleAction('archive')}>
                        <Archive size={16} className="mr-2 text-muted-foreground" />
                        {t('card.archive')}
                      </DropdownMenuItem>
                    )}
                  </>
                )}
                {skill.type === 'prebuilt' && onLifecycleAction && (
                  <>
                    {skill.has_upstream_update && (
                      <DropdownMenuItem onClick={() => handleLifecycleAction('accept-upstream')}>
                        <ArrowUpCircle size={16} className="mr-2 text-blue-500" />
                        {t('card.acceptUpstream')}
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuItem onClick={() => handleLifecycleAction('reset-to-default')}>
                      <Undo2 size={16} className="mr-2 text-muted-foreground" />
                      {t('card.resetToDefault')}
                    </DropdownMenuItem>
                  </>
                )}
                {showDeleteButton && (
                  <DropdownMenuItem onClick={handleDelete} className="text-destructive focus:text-destructive">
                    <Trash2 size={16} className="mr-2" />
                    {t('card.delete')}
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        <div className="mt-4 flex items-center justify-between">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="secondary" className={cn('text-xs', categoryColor)}>
              {t(`categories.${category}` as const)}
            </Badge>
            {skill.tags.slice(0, 2).map((tag) => {
              const key = `tagLabels.${tag.toLowerCase()}` as Parameters<typeof t>[0];
              const translated = t.has(key) ? t(key) : tag;
              return (
                <Badge key={tag} variant="outline" className="text-xs">
                  {translated}
                </Badge>
              );
            })}
            {skill.tags.length > 2 && (
              <Badge variant="outline" className="text-xs">
                +{skill.tags.length - 2}
              </Badge>
            )}
          </div>

          <div className="flex items-center gap-2">
            {skill.token_cost != null && skill.token_cost > 0 && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Badge
                    variant="outline"
                    className={cn(
                      'text-xs tabular-nums',
                      skill.token_cost < 500
                        ? 'border-green-300 text-green-600 dark:border-green-700 dark:text-green-400'
                        : skill.token_cost < 2000
                          ? 'border-amber-300 text-amber-600 dark:border-amber-700 dark:text-amber-400'
                          : 'border-red-300 text-red-600 dark:border-red-700 dark:text-red-400',
                    )}
                  >
                    {skill.token_cost.toLocaleString()} tok
                  </Badge>
                </TooltipTrigger>
                <TooltipContent>{t('card.tokenCostTooltip', { count: skill.token_cost })}</TooltipContent>
              </Tooltip>
            )}
            {skill.type === 'prebuilt' && (
              <Badge
                variant="outline"
                className="text-xs border-blue-300 text-blue-600 dark:border-blue-700 dark:text-blue-400"
              >
                {t('card.prebuilt')}
              </Badge>
            )}
            {skill.type === 'local' && (
              <div className="flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
                <FolderOpen size={14} />
                <span>{t('card.local')}</span>
              </div>
            )}
            <span className="text-xs text-muted-foreground">v{skill.version}</span>
          </div>
        </div>
      </div>
    );
  },
);

SkillCard.displayName = 'SkillCard';

export { getSkillStatus };
export default SkillCard;
