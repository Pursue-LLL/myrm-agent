/**
 * [INPUT]
 * - @/services/memory/crossAgent: ComposableContextResponseDTO, ContextLayerDTO
 * - @/components/primitives/badge: Badge
 * - lucide-react: Layers, Cpu, ShieldCheck, Lock, Share2, Sparkles
 *
 * [OUTPUT]
 * - ComposableContextProjectionView: Visualizes 4-layer virtual reference context projection, token distribution, and KV cache reuse metrics.
 *
 * [POS]
 * Sub-component for CrossAgentConflictArbitrationCard in command-center.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React from 'react';
import {
  Cpu,
  Layers,
  Lock,
  Share2,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';

import { Badge } from '@/components/primitives/badge';
import type {
  ComposableContextResponseDTO,
  ContextLayerDTO,
} from '@/services/memory/crossAgent';

interface ComposableContextProjectionViewProps {
  projection: ComposableContextResponseDTO;
}

function getLayerKindBadge(layerKind: string): { label: string; className: string } {
  switch (layerKind) {
    case 'profile_tools':
      return {
        label: 'Layer 2: Profile & Tools',
        className: 'border-blue-500/40 text-blue-600 dark:text-blue-400 bg-blue-500/10',
      };
    case 'global_ground_truth':
      return {
        label: 'Layer 3: Global Ground Truth',
        className: 'border-emerald-500/40 text-emerald-600 dark:text-emerald-400 bg-emerald-500/10',
      };
    case 'private_scratchpad':
      return {
        label: 'Layer 1: Private Scratchpad',
        className: 'border-purple-500/40 text-purple-600 dark:text-purple-400 bg-purple-500/10',
      };
    case 'ephemeral_handoff':
      return {
        label: 'Layer 4: Ephemeral Handoff',
        className: 'border-amber-500/40 text-amber-600 dark:text-amber-400 bg-amber-500/10',
      };
    default:
      return {
        label: layerKind,
        className: 'border-muted text-muted-foreground bg-muted/20',
      };
  }
}

export function ComposableContextProjectionView({
  projection,
}: ComposableContextProjectionViewProps) {
  return (
    <div className="space-y-4">
      {/* HUD Header / KV Cache Fingerprint */}
      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 pb-3">
          <div className="flex items-center gap-2">
            <Cpu className="h-4 w-4 text-primary" />
            <span className="text-sm font-semibold text-foreground">
              4层可组合上下文投影 HUD (Agent: {projection.agent_id})
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="border-primary/40 bg-primary/10 text-primary text-xs">
              总 Token: {projection.total_tokens}
            </Badge>
            <Badge variant="outline" className="border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-xs">
              <Sparkles className="mr-1 h-3 w-3 inline" />
              KV-Cache 命中预测: ~82%
            </Badge>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          <div className="rounded border border-border/60 bg-muted/20 p-2.5">
            <span className="text-muted-foreground font-mono block mb-1">
              🔒 稳定前缀哈希 (Layer 2 + 3):
            </span>
            <code className="text-foreground font-mono text-[11px] break-all select-all">
              {projection.cache_prefix_hash}
            </code>
          </div>
          <div className="rounded border border-border/60 bg-muted/20 p-2.5">
            <span className="text-muted-foreground font-mono block mb-1">
              ⚡ 协调会话 ID:
            </span>
            <span className="text-foreground font-mono">{projection.session_id}</span>
          </div>
        </div>
      </div>

      {/* Layer Cards */}
      <div className="space-y-3">
        {projection.layers.map((layer: ContextLayerDTO, idx: number) => {
          const badge = getLayerKindBadge(layer.layer_kind);
          return (
            <div
              key={`${layer.layer_kind}-${idx}`}
              className="rounded-lg border border-border/70 bg-card/60 p-3.5 space-y-2 hover:border-border transition-colors"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className={`text-xs ${badge.className}`}>
                    {badge.label}
                  </Badge>
                  <span className="text-xs font-medium text-foreground">
                    {layer.title}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  {layer.is_shared ? (
                    <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                      <Share2 className="h-3 w-3" /> 跨智能体共享
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-purple-600 dark:text-purple-400">
                      <Lock className="h-3 w-3" /> 本地隔离私有
                    </span>
                  )}
                  <span>•</span>
                  <span>{layer.token_count} tokens</span>
                </div>
              </div>

              <div className="rounded bg-muted/30 p-2.5 text-xs text-foreground/90 font-mono whitespace-pre-wrap max-h-36 overflow-y-auto">
                {layer.content}
              </div>

              <div className="text-[11px] text-muted-foreground font-mono flex items-center gap-1">
                <ShieldCheck className="h-3 w-3 text-muted-foreground" />
                <span>SHA-256: </span>
                <span className="truncate">{layer.content_hash}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
