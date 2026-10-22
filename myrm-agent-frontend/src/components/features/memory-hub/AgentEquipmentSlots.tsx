'use client';

/**
 * Game-like Agent Equipment Slots Component for cognitive loadout management.
 *
 * [INPUT] slots: EquipmentSlot[], totalEquipped: number, onUnequipSlot: (slotId: string) => void
 * [OUTPUT] AgentEquipmentSlots: Visual 4-slot loadout rack displaying equipped memory assets with unequip actions.
 * [POS] src/components/features/memory-hub/AgentEquipmentSlots.tsx
 */

import { memo } from 'react';
import {
  MessageSquare,
  Cpu,
  BookOpen,
  Network,
  X,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { EquipmentSlot, MemoryAssetType } from './memoryHubTypes';

export interface AgentEquipmentSlotsProps {
  slots: EquipmentSlot[];
  totalEquipped: number;
  maxSlots?: number;
  onUnequipSlot: (slotId: string) => void;
  onSelectEmptySlot?: (slot: EquipmentSlot) => void;
  className?: string;
}

const SLOT_ICONS: Record<MemoryAssetType, typeof MessageSquare> = {
  chat_memory: MessageSquare,
  skill: Cpu,
  wiki: BookOpen,
  code_graph: Network,
};

export const AgentEquipmentSlots = memo(function AgentEquipmentSlots({
  slots,
  totalEquipped,
  maxSlots = 4,
  onUnequipSlot,
  onSelectEmptySlot,
  className,
}: AgentEquipmentSlotsProps) {
  const t = useTranslations('memoryHub');

  return (
    <div
      className={cn(
        'rounded-2xl border border-border bg-card/60 backdrop-blur-sm p-4 shadow-sm flex flex-col gap-3',
        className,
      )}
      data-testid="agent-equipment-slots"
    >
      {/* Header bar: title & capacity tracker */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
            <ShieldCheck className="h-4 w-4" />
          </div>
          <div>
            <h3 className="font-semibold text-xs text-foreground">
              {t('equipmentLoadout') || 'Cognitive Memory Equipment Loadout'}
            </h3>
            <p className="text-[11px] text-muted-foreground">
              {t('equipmentSubtitle') || 'Mounted memory assets active in the current cognitive loop'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-muted/80 text-[11px] font-mono font-medium text-muted-foreground border border-border/60">
          <Sparkles className="h-3 w-3 text-amber-500" />
          <span>
            {totalEquipped} / {maxSlots}
          </span>
          <span className="text-[10px] text-muted-foreground/80">
            {t('equippedSlotsCount') || 'slots'}
          </span>
        </div>
      </div>

      {/* 4-Slots Grid Rack */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {slots.map((slot) => {
          const isEquipped = slot.equipped_asset !== null && slot.equipped_asset_id !== null;
          const primaryType: MemoryAssetType = slot.allowed_types[0] || 'chat_memory';
          const Icon = SLOT_ICONS[primaryType] || MessageSquare;

          if (isEquipped && slot.equipped_asset) {
            const asset = slot.equipped_asset;
            return (
              <div
                key={slot.slot_id}
                className="relative flex flex-col justify-between p-3 rounded-xl border border-primary/40 bg-primary/5 hover:border-primary/60 transition-all shadow-xs group"
                data-testid={`equipped-slot-${slot.slot_id}`}
              >
                <div>
                  <div className="flex items-center justify-between gap-1 mb-1.5">
                    <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-primary">
                      <Icon className="h-3 w-3 flex-shrink-0" />
                      <span>{slot.slot_name}</span>
                    </span>

                    <button
                      type="button"
                      onClick={() => {
                        onUnequipSlot(slot.slot_id);
                      }}
                      title={t('unequip') || 'Unequip asset'}
                      aria-label={`Unequip from ${slot.slot_name}`}
                      className="p-1 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                      data-testid={`unequip-btn-${slot.slot_id}`}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>

                  <h5 className="font-semibold text-xs text-foreground line-clamp-1 mb-0.5">
                    {asset.name}
                  </h5>
                  <p className="text-[10px] text-muted-foreground line-clamp-2 leading-relaxed">
                    {asset.description}
                  </p>
                </div>

                <div className="pt-2 mt-2 border-t border-primary/20 flex items-center justify-between text-[10px] text-muted-foreground font-mono">
                  <span className="uppercase text-[9px] font-semibold text-primary">
                    {asset.acl_scope}
                  </span>
                  <span>{Math.round(asset.size_bytes / 1024)} KB</span>
                </div>
              </div>
            );
          }

          // Empty Slot State
          return (
            <button
              key={slot.slot_id}
              type="button"
              onClick={() => {
                if (onSelectEmptySlot) {
                  onSelectEmptySlot(slot);
                }
              }}
              className="flex flex-col items-center justify-center p-4 rounded-xl border-2 border-dashed border-border/80 bg-muted/20 hover:bg-muted/40 hover:border-primary/40 transition-all text-center select-none group min-h-[108px]"
              data-testid={`empty-slot-${slot.slot_id}`}
            >
              <div className="p-2 rounded-full bg-muted/50 text-muted-foreground group-hover:text-primary group-hover:bg-primary/10 transition-colors mb-1.5">
                <Icon className="h-4 w-4" />
              </div>
              <span className="text-[11px] font-semibold text-muted-foreground group-hover:text-foreground">
                {slot.slot_name}
              </span>
              <span className="text-[10px] text-muted-foreground/70 mt-0.5">
                {t('clickToMount') || 'Available for mount'}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
});
