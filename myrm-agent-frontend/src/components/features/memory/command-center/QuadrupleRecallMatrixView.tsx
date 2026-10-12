/**
 * [INPUT]
 * @/services/memory::(channel_hits_count, fused_candidates_count, channel_weights)
 * lucide-react::(Share2, Sparkles, BookOpen, Layers, Network)
 *
 * [OUTPUT]
 * Component: QuadrupleRecallMatrixView
 *
 * [POS]
 * Matrix dashboard displaying 4-channel parallel recall distribution and RRF fusion metrics.
 * Shows Graph, Vector, Lexical, and Metadata hits alongside multi-channel synergy boost.
 * A11y compliant: Semantic sectioning, native labels, zero div role="status".
 * Strict typing: Zero `any`. Single file < 200 lines.
 */

import React from 'react';
import { Share2, Sparkles, BookOpen, Layers, Network } from 'lucide-react';

interface QuadrupleRecallMatrixViewProps {
  channelHits: Record<string, number>;
  fusedCandidatesCount: number;
  channelWeights: Record<string, number>;
}

const CHANNELS_CONFIG = [
  {
    id: 'graph',
    name: 'Graph 拓扑通道',
    description: '实体关联与拓扑锚点精准召回',
    icon: Share2,
    colorClass: 'text-blue-500 bg-blue-500/10 border-blue-500/20',
  },
  {
    id: 'vector',
    name: 'Vector 稠密通道',
    description: '语义嵌入近邻与跨语义关联',
    icon: Sparkles,
    colorClass: 'text-purple-500 bg-purple-500/10 border-purple-500/20',
  },
  {
    id: 'lexical',
    name: 'Lexical 词法通道',
    description: 'FTS5 / BM25 关键词精确匹配',
    icon: BookOpen,
    colorClass: 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20',
  },
  {
    id: 'metadata',
    name: 'Metadata 过滤通道',
    description: '结构化属性与环境约束硬匹配',
    icon: Layers,
    colorClass: 'text-amber-500 bg-amber-500/10 border-amber-500/20',
  },
];

export const QuadrupleRecallMatrixView: React.FC<QuadrupleRecallMatrixViewProps> = ({
  channelHits,
  fusedCandidatesCount,
  channelWeights,
}) => {
  return (
    <section
      aria-label="四路并行召回与融合矩阵"
      className="p-4 rounded-lg border border-border/80 bg-card/40 space-y-3.5"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="p-1 rounded bg-primary/10 text-primary">
            <Network className="w-3.5 h-3.5" aria-hidden="true" />
          </div>
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            四路并行召回 &amp; 多通道融合矩阵
          </h4>
        </div>

        <span className="px-2.5 py-0.5 rounded text-xs font-mono font-medium bg-primary/10 text-primary border border-primary/20">
          去重融合候选: {fusedCandidatesCount} 条
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
        {CHANNELS_CONFIG.map((channel) => {
          const hits = channelHits[channel.id] ?? 0;
          const weight = channelWeights[channel.id] ?? 1.0;
          const Icon = channel.icon;

          return (
            <div
              key={channel.id}
              className={`p-3 rounded-md border flex flex-col justify-between transition-all ${channel.colorClass}`}
            >
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold flex items-center gap-1.5">
                    <Icon className="w-3.5 h-3.5" aria-hidden="true" />
                    {channel.name}
                  </span>
                  <span className="text-sm font-bold font-mono">{hits} 命中</span>
                </div>
                <p className="text-[11px] text-muted-foreground line-clamp-1">
                  {channel.description}
                </p>
              </div>

              <div className="mt-2.5 pt-2 border-t border-border/40 flex items-center justify-between text-[11px] font-mono text-muted-foreground">
                <span>权重乘数:</span>
                <span className="font-semibold text-foreground">{weight.toFixed(2)}x</span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
};
