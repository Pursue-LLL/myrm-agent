/**
 * [INPUT]: TurnContextInjectionManifest, TurnProvenanceDiffItem list, isOpen and onClose callbacks.
 * [OUTPUT]: TurnContextProvenanceAuditModal component visualizing turn context injection provenance and cross-turn diffs.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/TurnContextProvenanceAuditModal.tsx
 */

import React, { useState } from 'react';
import {
  DiffType,
  InjectionSourceKind,
  TurnContextChunkItem,
  TurnContextInjectionManifest,
  TurnProvenanceDiffItem,
} from './turnContextProvenanceTypes';

export interface TurnContextProvenanceAuditModalProps {
  isOpen: boolean;
  onClose: () => void;
  manifest: TurnContextInjectionManifest;
  diffItems?: TurnProvenanceDiffItem[];
  previousTurnId?: string;
}

export const TurnContextProvenanceAuditModal: React.FC<TurnContextProvenanceAuditModalProps> = ({
  isOpen,
  onClose,
  manifest,
  diffItems = [],
  previousTurnId,
}) => {
  const [activeTab, setActiveTab] = useState<'manifest' | 'diff'>('manifest');
  const [copiedSha, setCopiedSha] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleCopySha = (sha: string) => {
    navigator.clipboard?.writeText(sha);
    setCopiedSha(sha);
    setTimeout(() => setCopiedSha(null), 2000);
  };

  const handleExportJson = () => {
    const jsonStr = JSON.stringify(manifest, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${manifest.session_id}_${manifest.turn_id}_manifest.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const getSourceKindColor = (kind: InjectionSourceKind) => {
    switch (kind) {
      case 'system_prompt':
        return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
      case 'memory':
        return 'bg-purple-500/20 text-purple-400 border-purple-500/30';
      case 'skill':
        return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
      case 'mcp_server':
        return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
      case 'workspace_file':
        return 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30';
      case 'tool_schema':
      default:
        return 'bg-slate-500/20 text-slate-400 border-slate-500/30';
    }
  };

  const getDiffBadge = (diffType: DiffType) => {
    switch (diffType) {
      case 'ADDED':
        return <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">✚ ADDED</span>;
      case 'REMOVED':
        return <span className="px-2 py-0.5 rounded text-[10px] bg-rose-500/20 text-rose-400 border border-rose-500/40">✖ REMOVED</span>;
      case 'MODIFIED':
        return <span className="px-2 py-0.5 rounded text-[10px] bg-amber-500/20 text-amber-400 border border-amber-500/40">✎ MODIFIED</span>;
      case 'UNCHANGED':
      default:
        return <span className="px-2 py-0.5 rounded text-[10px] bg-slate-700 text-slate-400 border border-slate-600">● UNCHANGED</span>;
    }
  };

  // 聚合各来源 token 占比色条
  const sourceTokens: Record<string, number> = {};
  manifest.chunks.forEach((c) => {
    sourceTokens[c.kind] = (sourceTokens[c.kind] || 0) + c.estimated_tokens;
  });
  const totalTokens = Math.max(1, manifest.total_tokens);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-4xl max-h-[88vh] flex flex-col shadow-2xl text-slate-100 overflow-hidden">
        {/* 头部 Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/90">
          <div className="space-y-0.5">
            <div className="flex items-center gap-2">
              <span className="p-1 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-bold text-xs">
                TURN-PROVENANCE
              </span>
              <h2 className="text-sm font-semibold text-white">
                逐轮上下文注入来源清单与可复现审计
              </h2>
            </div>
            <div className="flex items-center gap-3 text-xs text-slate-400">
              <span>会话: <span className="font-mono text-slate-300">{manifest.session_id}</span></span>
              <span>轮次: <span className="font-mono text-indigo-400">{manifest.turn_id}</span></span>
              <span>模型快照: <span className="font-mono text-teal-400">{manifest.model_snapshot_id}</span></span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleExportJson}
              className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded text-xs font-medium transition-colors border border-slate-700"
            >
              导出 .manifest.json
            </button>
            <button
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-white rounded hover:bg-slate-800 transition-colors"
            >
              ✕
            </button>
          </div>
        </div>

        {/* 来源 Token 占比可视化色条 */}
        <div className="p-4 bg-slate-950/40 border-b border-slate-800 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-400">
              单轮总注入算力: <strong className="text-white font-mono">{manifest.total_tokens.toLocaleString()} Tokens</strong> ({manifest.total_chars.toLocaleString()} 字符)
            </span>
            <span className="text-[11px] text-slate-500">共装配 {manifest.chunks.length} 个来源 Chunk</span>
          </div>

          <div className="w-full h-3 bg-slate-800 rounded-full overflow-hidden flex">
            {Object.entries(sourceTokens).map(([kind, tokens]) => {
              const pct = (tokens / totalTokens) * 100;
              const colorClass =
                kind === 'system_prompt'
                  ? 'bg-blue-500'
                  : kind === 'memory'
                  ? 'bg-purple-500'
                  : kind === 'skill'
                  ? 'bg-emerald-500'
                  : kind === 'mcp_server'
                  ? 'bg-amber-500'
                  : 'bg-cyan-500';
              return (
                <div
                  key={kind}
                  style={{ width: `${pct}%` }}
                  className={`h-full ${colorClass}`}
                  title={`${kind}: ${tokens} tokens (${pct.toFixed(1)}%)`}
                />
              );
            })}
          </div>

          <div className="flex flex-wrap gap-3 text-[11px] text-slate-400">
            {Object.entries(sourceTokens).map(([kind, tokens]) => {
              const pct = ((tokens / totalTokens) * 100).toFixed(1);
              return (
                <div key={kind} className="flex items-center gap-1.5">
                  <span
                    className={`w-2 h-2 rounded-full ${
                      kind === 'system_prompt'
                        ? 'bg-blue-500'
                        : kind === 'memory'
                        ? 'bg-purple-500'
                        : kind === 'skill'
                        ? 'bg-emerald-500'
                        : kind === 'mcp_server'
                        ? 'bg-amber-500'
                        : 'bg-cyan-500'
                    }`}
                  />
                  <span className="capitalize">{kind.replace('_', ' ')}:</span>
                  <span className="font-mono text-slate-300">{tokens} ({pct}%)</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* 导航标签切换 */}
        <div className="px-4 pt-3 flex items-center gap-2 border-b border-slate-800 bg-slate-900">
          <button
            onClick={() => setActiveTab('manifest')}
            className={`px-3 py-1.5 text-xs font-medium border-b-2 transition-colors ${
              activeTab === 'manifest'
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            本轮装配清单 ({manifest.chunks.length})
          </button>
          <button
            onClick={() => setActiveTab('diff')}
            className={`px-3 py-1.5 text-xs font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === 'diff'
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            跨轮次差异比对
            {diffItems.length > 0 && (
              <span className="px-1.5 py-0.2 rounded-full bg-slate-800 text-[10px] text-slate-300">
                {diffItems.length}
              </span>
            )}
          </button>
        </div>

        {/* 主体内容滚动区 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {activeTab === 'manifest' ? (
            <div className="overflow-x-auto border border-slate-800 rounded-lg">
              <table className="w-full text-xs text-left text-slate-300">
                <thead className="bg-slate-800/60 text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="px-3 py-2 font-medium">顺序</th>
                    <th className="px-3 py-2 font-medium">类型</th>
                    <th className="px-3 py-2 font-medium">来源标识 (source_id)</th>
                    <th className="px-3 py-2 font-medium">Tokens</th>
                    <th className="px-3 py-2 font-medium">SHA256 指纹</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {manifest.chunks.map((chunk: TurnContextChunkItem) => (
                    <tr key={chunk.chunk_id} className="hover:bg-slate-800/30">
                      <td className="px-3 py-2 font-mono text-slate-500">#{chunk.order_index}</td>
                      <td className="px-3 py-2">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${getSourceKindColor(chunk.kind)}`}>
                          {chunk.kind}
                        </span>
                      </td>
                      <td className="px-3 py-2 font-mono text-slate-200">{chunk.source_id}</td>
                      <td className="px-3 py-2 font-mono text-indigo-300">
                        {chunk.estimated_tokens} ({chunk.content_chars}字)
                      </td>
                      <td className="px-3 py-2 font-mono text-[11px] text-slate-400 flex items-center gap-2">
                        <span>{chunk.content_sha256.slice(0, 12)}...</span>
                        <button
                          onClick={() => handleCopySha(chunk.content_sha256)}
                          className="text-[10px] px-1 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
                        >
                          {copiedSha === chunk.content_sha256 ? '已复制' : '复制'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="text-xs text-slate-400">
                对比上轮: <span className="font-mono text-slate-200">{previousTurnId || '未指定'}</span> ➔ 当前轮: <span className="font-mono text-indigo-400">{manifest.turn_id}</span>
              </div>

              {diffItems.length === 0 ? (
                <div className="p-8 text-center text-slate-500 text-xs border border-dashed border-slate-800 rounded-lg">
                  暂无跨轮比对数据（可点击比对或上报前序轮次）
                </div>
              ) : (
                <div className="overflow-x-auto border border-slate-800 rounded-lg">
                  <table className="w-full text-xs text-left text-slate-300">
                    <thead className="bg-slate-800/60 text-slate-400 border-b border-slate-800">
                      <tr>
                        <th className="px-3 py-2 font-medium">差异状态</th>
                        <th className="px-3 py-2 font-medium">来源类型</th>
                        <th className="px-3 py-2 font-medium">来源标识 (source_id)</th>
                        <th className="px-3 py-2 font-medium">Token 增减量</th>
                        <th className="px-3 py-2 font-medium">指纹演变</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
                      {diffItems.map((diff) => (
                        <tr key={diff.source_id} className="hover:bg-slate-800/30">
                          <td className="px-3 py-2">{getDiffBadge(diff.diff_type)}</td>
                          <td className="px-3 py-2">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${getSourceKindColor(diff.kind)}`}>
                              {diff.kind}
                            </span>
                          </td>
                          <td className="px-3 py-2 font-mono text-slate-200">{diff.source_id}</td>
                          <td className="px-3 py-2 font-mono">
                            <span className={diff.token_delta > 0 ? 'text-amber-400' : diff.token_delta < 0 ? 'text-emerald-400' : 'text-slate-400'}>
                              {diff.token_delta > 0 ? `+${diff.token_delta}` : diff.token_delta}
                            </span>
                          </td>
                          <td className="px-3 py-2 font-mono text-[11px] text-slate-400">
                            {diff.diff_type === 'MODIFIED'
                              ? `${diff.previous_sha256?.slice(0, 8)}... ➔ ${diff.current_sha256?.slice(0, 8)}...`
                              : diff.diff_type === 'ADDED'
                              ? `✚ ${diff.current_sha256?.slice(0, 8)}...`
                              : diff.diff_type === 'REMOVED'
                              ? `✖ ${diff.previous_sha256?.slice(0, 8)}...`
                              : '一致'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
