/**
 * [INPUT]
 * ./agent-icons::AgentIcon (POS: 内置智能体视觉标识系统)
 * @/lib/utils/avatar-utils::parseAvatarUrl (POS: 智能体头像解析工具层)
 * @/lib/utils::cn (POS: Tailwind class 合并工具)
 *
 * [OUTPUT]
 * AgentAvatar: 智能体头像组件，支持 icon/emoji/image/首字母四种模式
 *
 * [POS]
 * 智能体头像统一渲染层。根据 avatar 字符串前缀自动选择渲染策略：
 * icon: → 定制 SVG 符号，emoji: → emoji，home:///URL → 图片，否则 → 首字母。
 */
import Image from 'next/image';
import { cn } from '@/lib/utils';
import { AgentIcon } from './agent-icons';
import { parseAvatarUrl } from '@/lib/utils/avatar-utils';

interface AgentAvatarProps {
  url?: string | null;
  name?: string;
  agentId?: string;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

const FALLBACK_SIZE_MAP = {
  sm: 'h-7 w-7 text-sm',
  md: 'h-9 w-9 text-base',
  lg: 'h-12 w-12 text-xl',
} as const;

export function AgentAvatar({ url, name, agentId, className, size = 'md' }: AgentAvatarProps) {
  const initial = name ? name.charAt(0).toUpperCase() : 'A';
  const parsed = parseAvatarUrl(url, agentId);

  if (parsed?.type === 'icon') {
    return <AgentIcon iconId={parsed.iconId} size={size} className={className} />;
  }

  const sizeClass = FALLBACK_SIZE_MAP[size];

  return (
    <div className={cn('relative flex shrink-0 overflow-hidden rounded-full bg-primary/10', sizeClass, className)}>
      {parsed?.type === 'emoji' ? (
        <div className="flex h-full w-full items-center justify-center rounded-full">{parsed.emoji}</div>
      ) : parsed?.type === 'image' ? (
        <Image
          src={parsed.src}
          alt={name || 'Agent'}
          fill
          className="aspect-square object-cover"
          unoptimized={parsed.src.startsWith('http://') || parsed.src.startsWith('https://')}
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center rounded-full text-primary font-medium">
          {initial}
        </div>
      )}
    </div>
  );
}
