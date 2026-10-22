'use client';

/**
 * Top-level Memory Asset Hub & Equipment Loadout Dashboard.
 *
 * [INPUT] agentId?: string, projectId?: string
 * [OUTPUT] MemoryAssetHub: 4-tier cognitive asset catalog, game-like equipment slots, and ACL security drawer.
 * [POS] src/components/features/memory-hub/MemoryAssetHub.tsx
 */

import { memo, useState, useEffect, useCallback, useMemo } from 'react';
import {
  Search,
  Layers,
  MessageSquare,
  Cpu,
  BookOpen,
  Network,
  Plus,
  RefreshCw,
  FolderLock,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type {
  AclScope,
  AclUpdatePayload,
  AgentEquipmentSummary,
  CreateAssetPayload,
  EquipmentSlot,
  MemoryAsset,
  MemoryAssetType,
} from './memoryHubTypes';
import { memoryHubService } from './memoryHubService';
import { MemoryAssetCard } from './MemoryAssetCard';
import { AgentEquipmentSlots } from './AgentEquipmentSlots';
import { AssetAclDrawer } from './AssetAclDrawer';

export interface MemoryAssetHubProps {
  agentId?: string;
  projectId?: string;
  className?: string;
}

type TabFilter = 'all' | MemoryAssetType;

export const MemoryAssetHub = memo(function MemoryAssetHub({
  agentId = 'default-agent',
  projectId = 'default-project',
  className,
}: MemoryAssetHubProps) {
  const t = useTranslations('memoryHub');

  const [activeTab, setActiveTab] = useState<TabFilter>('all');
  const [aclFilter, setAclFilter] = useState<'all' | AclScope>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [assets, setAssets] = useState<MemoryAsset[]>([]);
  const [equipment, setEquipment] = useState<AgentEquipmentSummary | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // ACL Drawer State
  const [aclTargetAsset, setAclTargetAsset] = useState<MemoryAsset | null>(null);
  const [isAclDrawerOpen, setIsAclDrawerOpen] = useState(false);

  // Load Assets and Equipment Summary
  const refreshData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [fetchedAssets, fetchedEquip] = await Promise.all([
        memoryHubService.listAssets({ agentId, projectId }),
        memoryHubService.getAgentEquipment(agentId),
      ]);
      setAssets(fetchedAssets);
      setEquipment(fetchedEquip);
    } finally {
      setIsLoading(false);
    }
  }, [agentId, projectId]);

  useEffect(() => {
    void refreshData();
  }, [refreshData]);

  // Set of equipped asset IDs for O(1) membership check
  const equippedAssetIds = useMemo(() => {
    if (!equipment) {
      return new Set<string>();
    }
    return new Set(
      equipment.slots
        .map((s) => s.equipped_asset_id)
        .filter((id): id is string => id !== null),
    );
  }, [equipment]);

  // Filtered Assets
  const filteredAssets = useMemo(() => {
    return assets.filter((asset) => {
      if (activeTab !== 'all' && asset.asset_type !== activeTab) {
        return false;
      }
      if (aclFilter !== 'all' && asset.acl_scope !== aclFilter) {
        return false;
      }
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchesName = asset.name.toLowerCase().includes(query);
        const matchesDesc = asset.description.toLowerCase().includes(query);
        const matchesTags = asset.tags.some((tag) => tag.toLowerCase().includes(query));
        if (!matchesName && !matchesDesc && !matchesTags) {
          return false;
        }
      }
      return true;
    });
  }, [assets, activeTab, aclFilter, searchQuery]);

  // Equip handler: find appropriate slot based on asset type
  const handleEquip = useCallback(
    async (asset: MemoryAsset) => {
      if (!equipment) {
        return;
      }
      // Target slot that accepts this asset type
      const targetSlot = equipment.slots.find((s) => s.allowed_types.includes(asset.asset_type));
      if (!targetSlot) {
        return;
      }

      const updated = await memoryHubService.equipAsset(agentId, targetSlot.slot_id, asset.id);
      setEquipment(updated);
    },
    [agentId, equipment],
  );

  // Unequip handler
  const handleUnequip = useCallback(
    async (asset: MemoryAsset) => {
      if (!equipment) {
        return;
      }
      const slot = equipment.slots.find((s) => s.equipped_asset_id === asset.id);
      if (!slot) {
        return;
      }

      const updated = await memoryHubService.unequipAsset(agentId, slot.slot_id);
      setEquipment(updated);
    },
    [agentId, equipment],
  );

  // Unequip directly from Slot
  const handleUnequipSlot = useCallback(
    async (slotId: string) => {
      const updated = await memoryHubService.unequipAsset(agentId, slotId);
      setEquipment(updated);
    },
    [agentId],
  );

  // Empty slot clicked -> filter catalog to that type
  const handleSelectEmptySlot = useCallback((slot: EquipmentSlot) => {
    const firstAllowed = slot.allowed_types[0];
    if (firstAllowed) {
      setActiveTab(firstAllowed);
    }
  }, []);

  // ACL Drawer open / save
  const handleOpenAcl = useCallback((asset: MemoryAsset) => {
    setAclTargetAsset(asset);
    setIsAclDrawerOpen(true);
  }, []);

  const handleSaveAcl = useCallback(
    async (assetId: string, payload: AclUpdatePayload) => {
      await memoryHubService.updateAssetAcl(assetId, payload, agentId);
      await refreshData();
    },
    [agentId, refreshData],
  );

  // Quick Create demo asset
  const handleQuickCreate = useCallback(async () => {
    const assetTypes: MemoryAssetType[] = ['chat_memory', 'skill', 'wiki', 'code_graph'];
    const randomType = assetTypes[Math.floor(Math.random() * assetTypes.length)] || 'wiki';
    const payload: CreateAssetPayload = {
      name: `Custom ${randomType.replace('_', ' ').toUpperCase()} #${Math.floor(Math.random() * 900 + 100)}`,
      description: 'Newly captured cognitive artifact with fine-grained isolation policies.',
      asset_type: randomType,
      acl_scope: 'team',
      content_preview: 'Knowledge graph node with references to active project files.',
      tags: ['custom', 'runtime'],
    };
    await memoryHubService.createAsset(payload, agentId, projectId);
    await refreshData();
  }, [agentId, projectId, refreshData]);

  return (
    <div
      className={cn('flex flex-col gap-5 p-4 w-full select-none text-foreground', className)}
      data-testid="memory-asset-hub"
    >
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/80 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-xl bg-primary/10 text-primary">
              <FolderLock className="h-5 w-5" />
            </div>
            <h2 className="text-base font-bold tracking-tight">
              {t('hubTitle') || 'Agent Cognitive Memory Hub & Equipment Deck'}
            </h2>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            {t('hubSubtitle') || 'Four-tier memory asset catalog with granular ACL isolation and game-like loadout equipment'}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              void refreshData();
            }}
            disabled={isLoading}
            className="p-1.5 rounded-lg border border-border bg-card hover:bg-muted text-muted-foreground hover:text-foreground transition-colors shadow-xs"
            title={t('refresh') || 'Refresh'}
            aria-label="Refresh"
          >
            <RefreshCw className={cn('h-4 w-4', isLoading && 'animate-spin')} />
          </button>

          <button
            type="button"
            onClick={handleQuickCreate}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-primary text-primary-foreground hover:opacity-90 active:scale-95 shadow-xs transition-all"
            data-testid="create-asset-btn"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>{t('createAsset') || 'Capture Asset'}</span>
          </button>
        </div>
      </div>

      {/* Equipment Slots Rack (Upper Deck) */}
      {equipment && (
        <AgentEquipmentSlots
          slots={equipment.slots}
          totalEquipped={equipment.total_equipped}
          maxSlots={equipment.max_slots}
          onUnequipSlot={handleUnequipSlot}
          onSelectEmptySlot={handleSelectEmptySlot}
        />
      )}

      {/* Filter and Search Bar (Middle Deck) */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 bg-muted/20 p-2.5 rounded-xl border border-border/70">
        {/* Category Tabs */}
        <div className="flex items-center gap-1 overflow-x-auto pb-1 md:pb-0">
          <button
            type="button"
            data-testid="tab-all"
            onClick={() => {
              setActiveTab('all');
            }}
            className={cn(
              'flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all whitespace-nowrap',
              activeTab === 'all'
                ? 'bg-card text-foreground shadow-xs font-semibold border border-border/80'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted/50',
            )}
          >
            <Layers className="h-3.5 w-3.5" />
            <span>{t('tabAll') || 'All Assets'}</span>
          </button>

          <button
            type="button"
            data-testid="tab-chat_memory"
            onClick={() => {
              setActiveTab('chat_memory');
            }}
            className={cn(
              'flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all whitespace-nowrap',
              activeTab === 'chat_memory'
                ? 'bg-card text-foreground shadow-xs font-semibold border border-border/80'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted/50',
            )}
          >
            <MessageSquare className="h-3.5 w-3.5 text-indigo-500" />
            <span>{t('typeChatMemory') || 'Chat Memory'}</span>
          </button>

          <button
            type="button"
            data-testid="tab-skill"
            onClick={() => {
              setActiveTab('skill');
            }}
            className={cn(
              'flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all whitespace-nowrap',
              activeTab === 'skill'
                ? 'bg-card text-foreground shadow-xs font-semibold border border-border/80'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted/50',
            )}
          >
            <Cpu className="h-3.5 w-3.5 text-amber-500" />
            <span>{t('typeSkill') || 'Skill Artifact'}</span>
          </button>

          <button
            type="button"
            data-testid="tab-wiki"
            onClick={() => {
              setActiveTab('wiki');
            }}
            className={cn(
              'flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all whitespace-nowrap',
              activeTab === 'wiki'
                ? 'bg-card text-foreground shadow-xs font-semibold border border-border/80'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted/50',
            )}
          >
            <BookOpen className="h-3.5 w-3.5 text-emerald-500" />
            <span>{t('typeWiki') || 'Wiki Knowledge'}</span>
          </button>

          <button
            type="button"
            data-testid="tab-code_graph"
            onClick={() => {
              setActiveTab('code_graph');
            }}
            className={cn(
              'flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all whitespace-nowrap',
              activeTab === 'code_graph'
                ? 'bg-card text-foreground shadow-xs font-semibold border border-border/80'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted/50',
            )}
          >
            <Network className="h-3.5 w-3.5 text-sky-500" />
            <span>{t('typeCodeGraph') || 'Code Graph'}</span>
          </button>
        </div>

        {/* Search & ACL Scope Filter */}
        <div className="flex items-center gap-2">
          <div className="relative flex-1 md:w-56">
            <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
              }}
              placeholder={t('searchPlaceholder') || 'Search assets, tags...'}
              className="w-full pl-8 pr-2.5 py-1 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary/50 text-foreground"
            />
          </div>

          <select
            value={aclFilter}
            onChange={(e) => {
              setAclFilter(e.target.value as 'all' | AclScope);
            }}
            className="px-2 py-1 text-xs rounded-lg border border-border bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50 font-medium"
            aria-label="ACL Filter"
          >
            <option value="all">{t('aclAll') || 'All Scopes'}</option>
            <option value="team">{t('aclTeam') || 'Team Shared'}</option>
            <option value="private">{t('aclPrivate') || 'Private Enclave'}</option>
            <option value="project">{t('aclProject') || 'Project Bound'}</option>
          </select>
        </div>
      </div>

      {/* Memory Asset Grid Catalog (Lower Deck) */}
      {filteredAssets.length === 0 ? (
        <div className="flex flex-col items-center justify-center p-12 rounded-xl border border-dashed border-border bg-muted/10 text-center">
          <FolderLock className="h-8 w-8 text-muted-foreground/60 mb-2" />
          <h4 className="font-semibold text-xs text-foreground">
            {t('emptyResults') || 'No cognitive assets match your filters'}
          </h4>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            {t('emptyResultsHint') || 'Try adjusting your search terms or create a new cognitive memory asset.'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {filteredAssets.map((asset) => (
            <MemoryAssetCard
              key={asset.id}
              asset={asset}
              isEquipped={equippedAssetIds.has(asset.id)}
              onEquip={handleEquip}
              onUnequip={handleUnequip}
              onOpenAcl={handleOpenAcl}
            />
          ))}
        </div>
      )}

      {/* ACL Security Drawer */}
      <AssetAclDrawer
        asset={aclTargetAsset}
        isOpen={isAclDrawerOpen}
        onClose={() => {
          setIsAclDrawerOpen(false);
          setAclTargetAsset(null);
        }}
        onSaveAcl={handleSaveAcl}
      />
    </div>
  );
});
