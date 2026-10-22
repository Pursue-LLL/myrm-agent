'use client';

/**
 * Memory Asset Card Component for 4-tier cognitive asset catalog.
 *
 * [INPUT] asset: MemoryAsset, isEquipped: boolean, onEquip, onUnequip, onOpenAcl
 * [OUTPUT] MemoryAssetCard: Interactive card presenting asset category, ACL badge, preview, and equipment action.
 * [POS] src/components/features/memory-hub/MemoryAssetCard.tsx
 */

import { memo } from 'react';
import {
  MessageSquare,
  Cpu,
  BookOpen,
  Network,
  ShieldAlert,
  Users,
  FolderGit2,
  Check,
  Plus,
  Shield,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { MemoryAsset, MemoryAssetType, AclScope } from './memoryHubTypes';

export interface MemoryAssetCardProps {
  asset: MemoryAsset;
  isEquipped?: boolean;
  onEquip?: (asset: MemoryAsset) => void;
  onUnequip?: (asset: MemoryAsset) => void;
  onOpenAcl?: (asset: MemoryAsset) => void;
  disabled?: boolean;
  className?: string;
}

const TYPE_CONFIG: Record<
  MemoryAssetType,
  {
    labelKey: string;
    defaultLabel: string;
    icon: typeof MessageSquare;
    badgeClass: string;
  }
> = {
  chat_memory: {
    labelKey: 'typeChatMemory',
    defaultLabel: 'Chat Memory',
    icon: MessageSquare,
    badgeClass: 'bg-indigo-500/10 text-indigo-500 border-indigo-500/20',
  },
  skill: {
    labelKey: 'typeSkill',
    defaultLabel: 'Skill Artifact',
    icon: Cpu,
    badgeClass: 'bg-amber-500/10 text-amber-500 border-amber-500/20',
  },
  wiki: {
    labelKey: 'typeWiki',
    defaultLabel: 'Wiki Knowledge',
    icon: BookOpen,
    badgeClass: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20',
  },
  code_graph: {
    labelKey: 'typeCodeGraph',
    defaultLabel: 'Code Graph',
    icon: Network,
    badgeClass: 'bg-sky-500/10 text-sky-500 border-sky-500/20',
  },
};

const ACL_CONFIG: Record<
  AclScope,
  {
    labelKey: string;
    defaultLabel: string;
    icon: typeof ShieldAlert;
    pillClass: string;
  }
> = {
  private: {
    labelKey: 'aclPrivate',
    defaultLabel: 'Private',
    icon: ShieldAlert,
    pillClass: 'bg-rose-500/10 text-rose-500 border-rose-500/20',
  },
  team: {
    labelKey: 'aclTeam',
    defaultLabel: 'Team Shared',
    icon: Users,
    pillClass: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  },
  project: {
    labelKey: 'aclProject',
    defaultLabel: 'Project Enclave',
    icon: FolderGit2,
    pillClass: 'bg-purple-500/10 text-purple-500 border-purple-500/20',
  },
};

export const MemoryAssetCard = memo(function MemoryAssetCard({
  asset,
  isEquipped = false,
  onEquip,
  onUnequip,
  onOpenAcl,
  disabled = false,
  className,
}: MemoryAssetCardProps) {
  const t = useTranslations('memoryHub');

  const typeMeta = TYPE_CONFIG[asset.asset_type];
  const aclMeta = ACL_CONFIG[asset.acl_scope];
  const TypeIcon = typeMeta.icon;
  const AclIcon = aclMeta.icon;

  const handleActionClick = () => {
    if (disabled) {
      return;
    }
    if (isEquipped) {
      if (onUnequip) {
        onUnequip(asset);
      }
    } else {
      if (onEquip) {
        onEquip(asset);
      }
    }
  };

  return (
    <div
      className={cn(
        'group relative flex flex-col justify-between rounded-xl border p-4 transition-all duration-200 select-none shadow-xs',
        isEquipped
          ? 'bg-primary/5 border-primary/50 shadow-sm ring-1 ring-primary/20'
          : 'bg-card border-border hover:border-border/80 hover:shadow-md',
        disabled && 'opacity-60 pointer-events-none',
        className,
      )}
      data-testid={`memory-asset-card-${asset.id}`}
    >
      <div>
        {/* Header: Type Badge & ACL Scope Capsule */}
        <div className="flex items-center justify-between gap-2 mb-2.5">
          <span
            className={cn(
              'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] font-semibold border',
              typeMeta.badgeClass,
            )}
          >
            <TypeIcon className="h-3.5 w-3.5 flex-shrink-0" />
            <span>{t(typeMeta.labelKey) || typeMeta.defaultLabel}</span>
          </span>

          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => {
                if (onOpenAcl) {
                  onOpenAcl(asset);
                }
              }}
              title={t('configureAcl') || 'Configure ACL'}
              aria-label={t('configureAcl') || 'Configure ACL'}
              className={cn(
                'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium border transition-colors hover:opacity-80',
                aclMeta.pillClass,
              )}
            >
              <AclIcon className="h-3 w-3 flex-shrink-0" />
              <span>{t(aclMeta.labelKey) || aclMeta.defaultLabel}</span>
              <Shield className="h-2.5 w-2.5 ml-0.5 opacity-60" />
            </button>
          </div>
        </div>

        {/* Title & Description */}
        <h4 className="font-semibold text-sm text-foreground line-clamp-1 mb-1">
          {asset.name}
        </h4>
        <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed mb-3">
          {asset.description}
        </p>

        {/* Content Snippet Preview */}
        {asset.content_preview && (
          <div className="bg-muted/40 rounded-lg p-2 font-mono text-[11px] text-muted-foreground border border-border/50 line-clamp-2 mb-3">
            {asset.content_preview}
          </div>
        )}
      </div>

      {/* Footer: Tags & Equip / Unequip CTA */}
      <div className="pt-2 border-t border-border/50 flex items-center justify-between gap-2 mt-auto">
        <div className="flex items-center gap-1 overflow-hidden">
          {asset.tags.slice(0, 2).map((tag) => (
            <span
              key={tag}
              className="px-1.5 py-0.5 rounded bg-muted/60 text-[10px] text-muted-foreground font-mono"
            >
              #{tag}
            </span>
          ))}
        </div>

        <button
          type="button"
          onClick={handleActionClick}
          disabled={disabled}
          className={cn(
            'inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold transition-all shadow-xs',
            isEquipped
              ? 'bg-primary/10 text-primary border border-primary/30 hover:bg-destructive/10 hover:text-destructive hover:border-destructive/30'
              : 'bg-primary text-primary-foreground hover:opacity-90 active:scale-95',
          )}
          data-testid={`equip-btn-${asset.id}`}
        >
          {isEquipped ? (
            <>
              <Check className="h-3.5 w-3.5" />
              <span>{t('equipped') || 'Equipped'}</span>
            </>
          ) : (
            <>
              <Plus className="h-3.5 w-3.5" />
              <span>{t('equip') || 'Equip'}</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
});
