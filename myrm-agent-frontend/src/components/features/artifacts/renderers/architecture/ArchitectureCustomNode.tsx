/**
 * [INPUT]
 * - @xyflow/react::Handle, Position, NodeProps
 * - @/lib/utils/classnameUtils::cn
 * - architecture/types::ArchitectureNodeIR, NodeCategory
 * - lucide-react::Globe, Shield, Server, Database, Zap, Layers, Cloud, etc.
 *
 * [OUTPUT]
 * - ArchitectureCustomNode: React.FC<NodeProps>
 * - ArchitectureNodeData
 *
 * [POS]
 * Architecture Node Presentation Layer — 渲染技术组件卡片、分类色彩、健康指示与演化 Diff 态。
 */
'use client';

import React, { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { cn } from '@/lib/utils/classnameUtils';
import type { ArchitectureNodeIR, NodeCategory } from './types';
import {
  Globe,
  Shield,
  Server,
  Database,
  Zap,
  Layers,
  Cloud,
  CheckCircle2,
  AlertTriangle,
  XCircle,
} from 'lucide-react';

const CATEGORY_STYLES: Record<
  NodeCategory | 'custom',
  { bg: string; border: string; text: string; icon: React.ElementType }
> = {
  frontend: {
    bg: 'bg-cyan-500/10 dark:bg-cyan-950/30',
    border: 'border-cyan-500/40 hover:border-cyan-500',
    text: 'text-cyan-700 dark:text-cyan-300',
    icon: Globe,
  },
  gateway: {
    bg: 'bg-amber-500/10 dark:bg-amber-950/30',
    border: 'border-amber-500/40 hover:border-amber-500',
    text: 'text-amber-700 dark:text-amber-300',
    icon: Shield,
  },
  backend: {
    bg: 'bg-emerald-500/10 dark:bg-emerald-950/30',
    border: 'border-emerald-500/40 hover:border-emerald-500',
    text: 'text-emerald-700 dark:text-emerald-300',
    icon: Server,
  },
  database: {
    bg: 'bg-purple-500/10 dark:bg-purple-950/30',
    border: 'border-purple-500/40 hover:border-purple-500',
    text: 'text-purple-700 dark:text-purple-300',
    icon: Database,
  },
  cache: {
    bg: 'bg-orange-500/10 dark:bg-orange-950/30',
    border: 'border-orange-500/40 hover:border-orange-500',
    text: 'text-orange-700 dark:text-orange-300',
    icon: Zap,
  },
  queue: {
    bg: 'bg-rose-500/10 dark:bg-rose-950/30',
    border: 'border-rose-500/40 hover:border-rose-500',
    text: 'text-rose-700 dark:text-rose-300',
    icon: Layers,
  },
  external: {
    bg: 'bg-slate-500/10 dark:bg-slate-900/30',
    border: 'border-slate-500/40 hover:border-slate-500',
    text: 'text-slate-700 dark:text-slate-300',
    icon: Cloud,
  },
  security: {
    bg: 'bg-red-500/10 dark:bg-red-950/30',
    border: 'border-red-500/40 hover:border-red-500',
    text: 'text-red-700 dark:text-red-300',
    icon: Shield,
  },
  custom: {
    bg: 'bg-blue-500/10 dark:bg-blue-950/30',
    border: 'border-blue-500/40 hover:border-blue-500',
    text: 'text-blue-700 dark:text-blue-300',
    icon: Server,
  },
};

export interface ArchitectureNodeData extends ArchitectureNodeIR {
  isHighlighted?: boolean;
  isDimmed?: boolean;
}

export const ArchitectureCustomNode: React.FC<NodeProps> = memo(({ data }) => {
  const node = data as unknown as ArchitectureNodeData;
  const rawCat = (node.category || node.type || 'backend').toLowerCase();
  const category = (rawCat in CATEGORY_STYLES ? rawCat : 'custom') as NodeCategory | 'custom';
  const style = CATEGORY_STYLES[category] || CATEGORY_STYLES.custom;
  const IconComponent = style.icon;

  const diffState = node.diffState;

  return (
    <div
      className={cn(
        'w-[220px] rounded-lg border p-3 shadow-xs transition-all duration-200 select-none backdrop-blur-xs',
        style.bg,
        style.border,
        node.isHighlighted && 'ring-2 ring-primary ring-offset-2 scale-102 z-20',
        node.isDimmed && 'opacity-25 grayscale',
        diffState === 'added' && 'ring-2 ring-emerald-500 border-emerald-500 bg-emerald-500/15',
        diffState === 'deleted' && 'ring-2 ring-rose-500 border-rose-500 border-dashed opacity-60 bg-rose-500/10',
        diffState === 'modified' && 'ring-2 ring-amber-500 border-amber-500 bg-amber-500/15',
      )}
    >
      <Handle type="target" position={Position.Top} className="!w-2 !h-2 !bg-muted-foreground/60" />
      <Handle type="source" position={Position.Bottom} className="!w-2 !h-2 !bg-muted-foreground/60" />
      <Handle type="target" position={Position.Left} className="!w-2 !h-2 !bg-muted-foreground/60" />
      <Handle type="source" position={Position.Right} className="!w-2 !h-2 !bg-muted-foreground/60" />

      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className={cn('p-1 rounded-md bg-background/80 shadow-2xs', style.text)}>
            <IconComponent size={15} />
          </div>
          <div className="min-w-0">
            <h4 className="text-xs font-semibold leading-tight truncate text-foreground">{node.label}</h4>
            {(node.group || node.group_id) && (
              <p className="text-[10px] text-muted-foreground truncate">{node.group || node.group_id}</p>
            )}
          </div>
        </div>

        {diffState ? (
          <span
            className={cn(
              'px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider',
              diffState === 'added' && 'bg-emerald-500 text-white',
              diffState === 'deleted' && 'bg-rose-500 text-white',
              diffState === 'modified' && 'bg-amber-500 text-white',
            )}
          >
            {diffState}
          </span>
        ) : node.status ? (
          <div className="shrink-0">
            {node.status === 'healthy' && <CheckCircle2 className="text-emerald-500" size={13} />}
            {node.status === 'warning' && <AlertTriangle className="text-amber-500" size={13} />}
            {node.status === 'degraded' && <XCircle className="text-rose-500" size={13} />}
          </div>
        ) : null}
      </div>

      {node.description && (
        <p className="mt-2 text-[11px] text-muted-foreground line-clamp-2 leading-snug">{node.description}</p>
      )}

      {node.technologies && node.technologies.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {node.technologies.slice(0, 3).map((tech) => (
            <span key={tech} className="text-[9px] px-1 py-0.5 rounded bg-background/60 border text-muted-foreground">
              {tech}
            </span>
          ))}
        </div>
      )}
    </div>
  );
});

ArchitectureCustomNode.displayName = 'ArchitectureCustomNode';
