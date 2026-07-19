/**
 * [INPUT]
 * @/lib/utils::cn (POS: Tailwind class 合并工具)
 *
 * [OUTPUT]
 * AGENT_ICON_REGISTRY: 内置智能体图标注册表（iconId → SVG + 渐变色）
 * AgentIcon: 按 iconId 渲染对应的定制几何符号组件
 *
 * [POS]
 * 内置智能体视觉标识系统。为每个内置智能体提供独一无二的 SVG 几何符号
 * 与渐变配色，取代通用 emoji/icon 库方案。
 */
'use client';

import React from 'react';
import { cn } from '@/lib/utils';
import * as LucideIcons from 'lucide-react';

interface AgentIconDef {
  svg: React.ReactNode;
  gradient: [string, string];
}

const ICON_SIZE = 20;

/**
 * Custom geometric SVG symbols for built-in agents.
 * Each icon is a hand-crafted abstract shape — not from any icon library.
 */
export const AGENT_ICON_REGISTRY: Record<string, AgentIconDef> = {
  general: {
    svg: (
      <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 3" />
        <circle cx="12" cy="12" r="1.5" fill="currentColor" />
      </svg>
    ),
    gradient: ['#8b5cf6', '#7c3aed'],
  },

  writer: {
    svg: (
      <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none">
        <path
          d="M6 18 L12 4 L18 18"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path d="M8 14 L16 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
    gradient: ['#f43f5e', '#e11d48'],
  },

  researcher: {
    svg: (
      <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="12" cy="12" r="6" stroke="currentColor" strokeWidth="1" opacity="0.6" />
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="0.75" opacity="0.3" />
      </svg>
    ),
    gradient: ['#06b6d4', '#0284c7'],
  },

  developer: {
    svg: (
      <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none">
        <path
          d="M8 7 L4 12 L8 17"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M16 7 L20 12 L16 17"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path d="M14 4 L10 20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
    gradient: ['#10b981', '#059669'],
  },

  translator: {
    svg: (
      <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none">
        <path
          d="M5 8 L12 8 M8.5 5 C8.5 5 7 11 5 13 M9 11 C9 11 11 14 13 15"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M14 10 L17 18 L20 10"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path d="M15 15 L19 15" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
      </svg>
    ),
    gradient: ['#f59e0b', '#d97706'],
  },

  'social-media': {
    svg: (
      <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none">
        <path
          d="M4 12 L10 6 L10 10 L20 10 L20 14 L10 14 L10 18 Z"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
      </svg>
    ),
    gradient: ['#d946ef', '#c026d3'],
  },

  'data-analyst': {
    svg: (
      <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none">
        <path d="M4 18 L4 14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M9 18 L9 10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M14 18 L14 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M19 18 L19 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M4 14 C7 8 14 5 19 8" stroke="currentColor" strokeWidth="1" strokeDasharray="2 2" opacity="0.5" />
      </svg>
    ),
    gradient: ['#0ea5e9', '#4f46e5'],
  },

  'product-manager': {
    svg: (
      <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none">
        <rect x="5" y="5" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
        <rect x="13" y="5" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
        <rect x="5" y="13" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
        <rect x="13" y="13" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.5" opacity="0.4" />
      </svg>
    ),
    gradient: ['#64748b', '#475569'],
  },

  tutor: {
    svg: (
      <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none">
        <path d="M12 4 L21 9 L12 14 L3 9 Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
        <path
          d="M6 11 L6 17 C6 17 9 20 12 20 C15 20 18 17 18 17 L18 11"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    ),
    gradient: ['#14b8a6', '#0891b2'],
  },

  // ─── New Templates ─────────────────────────────────────────────────────
  newsletter: {
    svg: (
      <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none">
        <rect x="4" y="5" width="16" height="14" rx="2" stroke="currentColor" strokeWidth="1.5" />
        <path d="M4 9 L12 13 L20 9" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      </svg>
    ),
    gradient: ['#ea580c', '#c2410c'],
  },

  design: {
    svg: (
      <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none">
        <circle cx="9" cy="9" r="4" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="15" cy="9" r="4" stroke="currentColor" strokeWidth="1.5" opacity="0.5" />
        <circle cx="12" cy="14" r="4" stroke="currentColor" strokeWidth="1.5" opacity="0.3" />
      </svg>
    ),
    gradient: ['#ec4899', '#db2777'],
  },

  video: {
    svg: (
      <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none">
        <rect x="3" y="6" width="13" height="12" rx="2" stroke="currentColor" strokeWidth="1.5" />
        <path
          d="M16 10 L21 7 L21 17 L16 14"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="9.5" cy="12" r="2" stroke="currentColor" strokeWidth="1" opacity="0.5" />
      </svg>
    ),
    gradient: ['#f97316', '#ea580c'],
  },

  seo: {
    svg: (
      <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none">
        <path
          d="M4 18 L8 14 L12 16 L16 8 L20 6"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="20" cy="6" r="2" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    ),
    gradient: ['#84cc16', '#16a34a'],
  },

  scheduler: {
    svg: (
      <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="1.5" />
        <path
          d="M12 7 L12 12 L16 14"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    ),
    gradient: ['#3b82f6', '#4338ca'],
  },

  meeting: {
    svg: (
      <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none">
        <rect x="5" y="4" width="14" height="16" rx="2" stroke="currentColor" strokeWidth="1.5" />
        <path d="M9 8 L15 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M9 12 L15 12" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" opacity="0.6" />
        <path d="M9 16 L13 16" stroke="currentColor" strokeWidth="1" strokeLinecap="round" opacity="0.4" />
      </svg>
    ),
    gradient: ['#8b5cf6', '#6d28d9'],
  },

  career: {
    svg: (
      <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="1.5" />
        <path d="M12 4 L12 8 M12 12 L17 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="12" cy="12" r="1.5" fill="currentColor" />
      </svg>
    ),
    gradient: ['#14b8a6', '#0d9488'],
  },

  finance: {
    svg: (
      <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none">
        <path d="M12 4 L12 20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <path
          d="M8 8 C8 6 10 5 12 5 C14 5 16 6 16 8 C16 10 14 11 12 11 C10 11 8 12 8 14 C8 16 10 17 12 17 C14 17 16 16 16 14"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
    ),
    gradient: ['#10b981', '#047857'],
  },

  travel: {
    svg: (
      <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none">
        <path
          d="M12 2 C12 2 8 8 8 13 C8 16.3 9.8 19 12 19 C14.2 19 16 16.3 16 13 C16 8 12 2 12 2 Z"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
        <circle cx="12" cy="13" r="2" fill="currentColor" opacity="0.4" />
      </svg>
    ),
    gradient: ['#0ea5e9', '#2563eb'],
  },

  email: {
    svg: (
      <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none">
        <path d="M4 8 L12 13 L20 8" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
        <path
          d="M4 8 L4 17 C4 18.1 4.9 19 6 19 L18 19 C19.1 19 20 18.1 20 17 L20 8"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    ),
    gradient: ['#64748b', '#334155'],
  },

  automation: {
    svg: (
      <svg width={ICON_SIZE} height={ICON_SIZE} viewBox="0 0 24 24" fill="none">
        <circle cx="6" cy="12" r="2.5" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="18" cy="7" r="2.5" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="18" cy="17" r="2.5" stroke="currentColor" strokeWidth="1.5" />
        <path d="M8.5 11 L15.5 8" stroke="currentColor" strokeWidth="1.2" />
        <path d="M8.5 13 L15.5 16" stroke="currentColor" strokeWidth="1.2" />
      </svg>
    ),
    gradient: ['#a855f7', '#7c3aed'],
  },
};

interface AgentIconProps {
  iconId: string;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const SIZE_MAP = {
  sm: 'w-7 h-7',
  md: 'w-9 h-9',
  lg: 'w-12 h-12',
} as const;

export function AgentIcon({ iconId, size = 'md', className }: AgentIconProps) {
  const def = AGENT_ICON_REGISTRY[iconId];
  if (!def) return null;

  const [from, to] = def.gradient;

  return (
    <div
      className={cn(SIZE_MAP[size], 'rounded-xl flex items-center justify-center shrink-0', className)}
      style={{
        background: `linear-gradient(135deg, ${from}20, ${to}30)`,
        color: from,
      }}
    >
      {def.svg}
    </div>
  );
}

/**
 * Resolve a kebab-case lucide icon name to its React component.
 * Returns the matched icon or LucideIcons.Bot as fallback.
 */
export function resolveLucideIcon(iconName: string): React.ComponentType<{ size?: number; className?: string }> {
  const componentName = iconName.split('-').map(s => s.charAt(0).toUpperCase() + s.slice(1)).join('');
  return (LucideIcons as Record<string, React.ComponentType<{ size?: number; className?: string }>>)[componentName] || LucideIcons.Bot;
}

export function LucideAgentIcon({ iconName, size = 'md', className }: { iconName: string, size?: 'sm' | 'md' | 'lg', className?: string }) {
  const IconComponent = resolveLucideIcon(iconName);

  const sizeMap = {
    sm: 16,
    md: 20,
    lg: 24,
  };
  const iconSize = sizeMap[size];

  return (
    <div className={cn(SIZE_MAP[size], 'rounded-xl flex items-center justify-center shrink-0 bg-primary/10 text-primary', className)}>
      <IconComponent size={iconSize} />
    </div>
  );
}
