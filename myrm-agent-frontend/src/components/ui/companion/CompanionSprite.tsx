'use client';

import { cn } from '@/lib/utils/classnameUtils';
import { IconGift } from '@/components/ui/icons/PremiumIcons';
import useCompanionStore from '@/store/useCompanionStore';
import useAgentStore from '@/store/useAgentStore';

import { getRarityAbilities } from './companionGenerator';
import { SPECIES_ICON_MAP, HAT_ICON_MAP } from './CompanionIcons';

import type { CompanionBones, Hat, Mood, Rarity } from './companionGenerator';

type AnimState = 'idle' | 'working' | 'bounce';

interface CompanionSpriteProps {
  bones: CompanionBones;
  animState: AnimState;
  speciesOverride?: string | null;
  hatOverride?: Hat | undefined;
  onClick?: () => void;
  isBirthday?: boolean;
}

const RARITY_GLOW: Record<Rarity, string> = {
  Common: '',
  Uncommon: 'drop-shadow(0 0 4px rgba(59,130,246,0.3))',
  Rare: 'drop-shadow(0 0 6px rgba(168,85,247,0.4))',
  Epic: 'drop-shadow(0 0 8px rgba(236,72,153,0.5)) drop-shadow(0 0 16px rgba(236,72,153,0.2))',
  Legendary: 'drop-shadow(0 0 12px rgba(234,179,8,0.6)) drop-shadow(0 0 24px rgba(234,179,8,0.3))',
};

const RARITY_RING: Record<Rarity, string> = {
  Common: '',
  Uncommon: '',
  Rare: '',
  Epic: 'ring-1 ring-pink-400/30',
  Legendary: 'ring-2 ring-amber-400/40',
};

const RARITY_COLOR: Record<Rarity, string> = {
  Common: 'text-foreground/70',
  Uncommon: 'text-blue-500',
  Rare: 'text-purple-500',
  Epic: 'text-pink-500',
  Legendary: 'text-amber-500',
};

const STATUS_ICONS: Record<string, { icon: string; className: string }> = {
  sleeping: { icon: 'z', className: 'text-muted-foreground opacity-60' },
  dizzy: { icon: '~', className: 'text-yellow-500 animate-spin' },
  celebrating: { icon: '*', className: 'text-amber-500 animate-bounce' },
  panting: { icon: '!', className: 'text-red-500 animate-pulse' },
};

const MOOD_ANIM: Record<Mood, string> = {
  neutral: '',
  happy: 'animate-companion-sway',
  curious: 'animate-companion-tilt',
  excited: 'animate-companion-bounce',
  sleepy: 'animate-companion-idle',
};

export default function CompanionSprite({
  bones,
  animState,
  speciesOverride,
  hatOverride,
  onClick,
  isBirthday,
}: CompanionSpriteProps) {
  const evolvedRarity = useCompanionStore((s) => s.evolvedRarity);
  const mascotStatus = useCompanionStore((s) => s.mascotStatus);
  const mood = useCompanionStore((s) => s.mood);
  const effectiveRarity: Rarity = (evolvedRarity ?? bones.rarity) as Rarity;
  const abilities = getRarityAbilities(effectiveRarity);

  const activeAgent = useAgentStore((s) => s.selectedAgent);
  const activeAgentId = activeAgent?.id ?? '';
  const avatar = activeAgent?.avatar_url;

  let species = speciesOverride ?? bones.species;
  let hat = hatOverride === undefined ? bones.hat : hatOverride;

  if (!speciesOverride) {
    const isEmojiAvatar = avatar && avatar.length <= 8 && !avatar.includes('/') && !avatar.includes('.');
    if (isEmojiAvatar) {
      species = avatar;
      if (hatOverride === undefined) {
        if (activeAgentId === 'builtin-developer') hat = '🔥';
        else if (activeAgentId === 'builtin-researcher') hat = '🎓';
        else if (activeAgentId === 'builtin-writer') hat = '🌸';
        else if (activeAgentId === 'builtin-meeting-scribe') hat = '🎀';
        else if (activeAgentId === 'builtin-product-manager') hat = '👑';
      }
    } else {
      if (activeAgentId === 'builtin-developer') {
        species = '🤖';
        if (hatOverride === undefined) hat = '🔥';
      } else if (activeAgentId === 'builtin-researcher') {
        species = '🦉';
        if (hatOverride === undefined) hat = '🎓';
      } else if (activeAgentId === 'builtin-writer') {
        species = '🦊';
        if (hatOverride === undefined) hat = '🌸';
      } else if (activeAgentId === 'builtin-meeting-scribe') {
        species = '🐼';
        if (hatOverride === undefined) hat = '🎀';
      } else if (activeAgentId === 'builtin-product-manager') {
        species = '🐙';
        if (hatOverride === undefined) hat = '👑';
      }
    }
  }

  const glow = RARITY_GLOW[effectiveRarity];
  const ring = RARITY_RING[effectiveRarity];
  const rarityColor = RARITY_COLOR[effectiveRarity];

  const SpeciesIcon = SPECIES_ICON_MAP[species];
  const HatIcon = hat ? HAT_ICON_MAP[hat] : null;
  const statusInfo = mascotStatus ? STATUS_ICONS[mascotStatus] : null;
  const hasActiveStatus = mascotStatus && mascotStatus !== 'sleeping' && mascotStatus !== 'idle';
  const moodAnim = hasActiveStatus ? '' : MOOD_ANIM[mood] || '';

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'relative flex flex-col items-center select-none cursor-pointer transition-transform rounded-full',
        animState === 'idle' && !moodAnim && 'animate-companion-idle',
        (animState === 'working' || mascotStatus === 'thinking') && 'animate-companion-working',
        animState === 'bounce' && 'animate-companion-bounce',
        mascotStatus === 'dizzy' && 'animate-bounce',
        moodAnim,
        ring,
      )}
      style={{ filter: glow || undefined }}
      aria-label="Companion"
    >
      {HatIcon ? (
        <span className={cn('leading-none -mb-0.5 z-10', rarityColor)}>
          <HatIcon size={14} />
        </span>
      ) : hat ? (
        <span className="text-xs leading-none -mb-1 z-10">{hat}</span>
      ) : null}

      <div className="relative">
        {SpeciesIcon ? (
          <span
            className={cn('block', rarityColor, (bones.shiny || abilities.legendaryFlair) && 'animate-shimmer-overlay')}
          >
            <SpeciesIcon size={28} />
          </span>
        ) : (
          <span
            className={cn(
              'text-2xl leading-none',
              (bones.shiny || abilities.legendaryFlair) && 'animate-shimmer-overlay',
            )}
          >
            {species}
          </span>
        )}
        {statusInfo && (
          <span
            className={cn(
              'absolute -top-1 -right-1 text-[10px] font-bold select-none pointer-events-none',
              statusInfo.className,
            )}
          >
            {statusInfo.icon}
          </span>
        )}
      </div>
      {isBirthday && (
        <span className="absolute -top-1 -right-2 text-xs">
          <IconGift />
        </span>
      )}
    </button>
  );
}
