'use client';

/**
 * [INPUT]
 * @/lib/utils/avatarUtils::parseAvatarUrl (POS: 头像地址解析)
 * @/components/agent/agent-icons::AgentIcon (POS: 内置智能体图标)
 * @/components/agent/lucide-icon-resolver::findLucideIcon (POS: 预设图标名解析，未知名称返回 null)
 *
 * [OUTPUT]
 * AgentIndicatorAvatar: 指示器按钮里的 20px 头像。
 *
 * [POS]
 * 输入区智能体指示器的头像。会话配置里的自定义头像优先（内置图标 / 渐变 / 图片 / emoji）；
 * 否则显示预设图标，预设没有可识别的图标就显示机器人占位。占位图块在已选择智能体时用渐变底加白色图标，
 * 未选择时是灰色底加灰色图标；预设的渐变由预设 id 稳定决定，同一个预设永远是同一种颜色。
 */

import type { ComponentType } from 'react';
import { useTranslations } from 'next-intl';
import { AiNetworkIcon, BotIcon } from 'hugeicons-react';
import { AgentIcon } from '@/components/agent/agent-icons';
import { findLucideIcon } from '@/components/agent/lucide-icon-resolver';
import { parseAvatarUrl } from '@/lib/utils/avatarUtils';
import { cn } from '@/lib/utils/classnameUtils';
import type { AgentConfig } from '@/store/chat/types/sessionConfig';

interface Gradient {
  from: string;
  to: string;
}

// Tailwind only generates classes it can read in the source, so every pair is spelled out.
const GRADIENTS: readonly Gradient[] = [
  { from: 'from-primary', to: 'to-violet-500' },
  { from: 'from-blue-500', to: 'to-cyan-500' },
  { from: 'from-emerald-500', to: 'to-teal-500' },
  { from: 'from-orange-500', to: 'to-amber-500' },
  { from: 'from-pink-500', to: 'to-rose-500' },
  { from: 'from-indigo-500', to: 'to-purple-500' },
];

const TILE = 'w-full h-full rounded flex items-center justify-center';

/** An index outside the palette falls back to the first pair instead of rendering a colorless tile. */
const gradientAt = (index: number): Gradient => GRADIENTS[index] ?? GRADIENTS[0];

const stableGradientIndex = (value: string): number => {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) | 0;
  }
  return (hash >>> 0) % GRADIENTS.length;
};

interface PlaceholderTileProps {
  icon: ComponentType<{ size?: number; className?: string }>;
  gradient: Gradient;
  selected: boolean;
}

function PlaceholderTile({ icon: Icon, gradient, selected }: PlaceholderTileProps) {
  return (
    <div
      className={cn(TILE, selected ? cn('bg-gradient-to-br', gradient.from, gradient.to) : 'bg-muted-foreground/20')}
    >
      <Icon size={12} className={selected ? 'text-white' : 'text-muted-foreground'} />
    </div>
  );
}

interface AgentIndicatorAvatarProps {
  agentConfig: AgentConfig | null;
  hasSelectedAgent: boolean;
}

export function AgentIndicatorAvatar({ agentConfig, hasSelectedAgent }: AgentIndicatorAvatarProps) {
  const t = useTranslations('agent.indicator');
  const parsed = parseAvatarUrl(agentConfig?.avatarUrl, agentConfig?.agentId);

  if (parsed?.type === 'icon') {
    return <AgentIcon iconId={parsed.iconId} size="sm" className="w-5 h-5" />;
  }
  if (parsed?.type === 'gradient') {
    const { from, to } = gradientAt(parsed.index);
    return (
      <div className={cn(TILE, 'bg-gradient-to-br', from, to)}>
        <AiNetworkIcon size={12} className="text-white" />
      </div>
    );
  }
  if (parsed?.type === 'image') {
    return (
      // oxlint-disable-next-line next/no-img-element -- the avatar is a user-supplied arbitrary address (remote or data URL), which next/image cannot optimize
      <img
        src={parsed.src}
        alt={agentConfig?.agentName || t('default')}
        className="w-full h-full rounded object-cover"
      />
    );
  }
  if (parsed?.type === 'emoji') {
    return <span className="text-xs">{parsed.emoji}</span>;
  }

  return (
    <PlaceholderTile
      icon={(agentConfig?.presetIcon ? findLucideIcon(agentConfig.presetIcon) : null) ?? BotIcon}
      gradient={agentConfig?.presetId ? gradientAt(stableGradientIndex(agentConfig.presetId)) : GRADIENTS[0]}
      selected={hasSelectedAgent}
    />
  );
}
