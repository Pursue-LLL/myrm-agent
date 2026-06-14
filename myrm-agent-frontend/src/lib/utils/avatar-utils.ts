/**
 * [INPUT]
 * @/components/agent/agent-icons::AGENT_ICON_REGISTRY (POS: 内置智能体视觉标识系统)
 *
 * [OUTPUT]
 * ParsedAvatar: 头像解析结果联合类型
 * parseAvatarUrl: 统一的 avatar URL 解析函数
 * isIconAvatar: 快捷判断是否为 icon 类型
 *
 * [POS]
 * 智能体头像解析工具层。提供 avatar URL 的统一解析逻辑，
 * 支持 icon:/lucide:/emoji:/home:///http(s):///gradient: 六种格式，
 * 消除各组件重复的解析实现。
 */

import { AGENT_ICON_REGISTRY } from '@/components/agent/agent-icons';

export type ParsedAvatar =
  | { type: 'icon'; iconId: string }
  | { type: 'emoji'; emoji: string }
  | { type: 'image'; src: string }
  | { type: 'gradient'; index: number }
  | { type: 'lucide'; iconName: string }
  | null;

/**
 * Parse an avatar URL string into a structured type.
 * Handles all supported formats:
 * - icon:{id}     → custom SVG icon from registry
 * - emoji:{char}  → emoji character
 * - home://{path} → user-uploaded file (requires agentId)
 * - http(s)://    → remote image URL
 * - gradient:{n}  → gradient index
 * - lucide:{name} → Lucide react icon
 */
export function parseAvatarUrl(url: string | null | undefined, agentId?: string): ParsedAvatar {
  if (!url) return null;

  if (url.startsWith('icon:')) {
    const iconId = url.slice(5);
    if (iconId in AGENT_ICON_REGISTRY) return { type: 'icon', iconId };
    return null;
  }

  if (url.startsWith('lucide:')) {
    return { type: 'lucide', iconName: url.slice(7) };
  }

  if (url.startsWith('emoji:')) {
    return { type: 'emoji', emoji: url.slice(6) };
  }

  if (url.startsWith('home://')) {
    if (!agentId) return null;
    const relativePath = url.slice(7);
    return { type: 'image', src: `/api/v1/user-agents/${agentId}/files/${relativePath}` };
  }

  if (url.startsWith('http://') || url.startsWith('https://')) {
    return { type: 'image', src: url };
  }

  if (url.startsWith('gradient:')) {
    const index = parseInt(url.slice(9), 10);
    if (!isNaN(index)) return { type: 'gradient', index };
    return null;
  }

  return null;
}

/**
 * Quick check: is this avatar URL an icon type?
 */
export function isIconAvatar(url: string | null | undefined): boolean {
  if (!url?.startsWith('icon:')) return false;
  return url.slice(5) in AGENT_ICON_REGISTRY;
}
