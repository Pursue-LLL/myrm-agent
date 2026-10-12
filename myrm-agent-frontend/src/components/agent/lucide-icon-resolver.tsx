/**
 * [INPUT]
 * lucide-react::Bot (POS: 回退图标)
 * lucide-react/dynamic::DynamicIcon, iconNames (POS: 按名称异步加载单个图标)
 *
 * [OUTPUT]
 * findLucideIcon: 按名称（kebab-case 或 PascalCase）解析图标组件，未知名称返回 null
 * resolveLucideIcon: 同上，未知名称回退为 Bot
 *
 * [POS]
 * 智能体/模板/蓝图的图标名来自服务端与组织市场数据，集合不封闭。
 * 禁止 `import * as` 整库引入——会把约 2000 个图标全部打进共享 chunk；
 * 这里每个图标只在首次渲染时才异步加载自己的 chunk。
 */
'use client';

import { Bot } from 'lucide-react';
import { DynamicIcon, iconNames, type IconName } from 'lucide-react/dynamic';
import type { ComponentType } from 'react';

type LucideComponent = ComponentType<{ size?: number; className?: string }>;

/** 去掉大小写与分隔符，让 `CheckSquare`、`check-square`、`grid-2x2` 落到同一个键。 */
const normalizeIconName = (name: string): string => name.toLowerCase().replace(/[^a-z0-9]/g, '');

let canonicalNames: Map<string, IconName> | null = null;

function getCanonicalNames(): Map<string, IconName> {
  if (canonicalNames === null) {
    canonicalNames = new Map(iconNames.map((name) => [normalizeIconName(name), name]));
  }
  return canonicalNames;
}

const componentCache = new Map<IconName, LucideComponent>();

function createLazyIcon(name: IconName): LucideComponent {
  function LazyLucideIcon({ size, className }: { size?: number; className?: string }) {
    return (
      <DynamicIcon
        name={name}
        size={size}
        className={className}
        fallback={() => <Bot size={size} className={className} />}
      />
    );
  }
  return LazyLucideIcon;
}

export function findLucideIcon(iconName: string): LucideComponent | null {
  const canonical = getCanonicalNames().get(normalizeIconName(iconName));
  if (canonical === undefined) {
    return null;
  }
  let component = componentCache.get(canonical);
  if (component === undefined) {
    component = createLazyIcon(canonical);
    componentCache.set(canonical, component);
  }
  return component;
}

export function resolveLucideIcon(iconName: string): LucideComponent {
  return findLucideIcon(iconName) ?? Bot;
}
