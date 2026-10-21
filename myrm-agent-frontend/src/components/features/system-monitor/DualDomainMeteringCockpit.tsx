/**
 * [INPUT]: DualDomainMeteringCockpitProps containing summary, records, and reconciliation statement.
 * [OUTPUT]: High-fidelity Dual-Domain Metering Cockpit with 3D cost attribution and SHA-256 audit statements.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/DualDomainMeteringCockpit.tsx
 */

import React, { useState } from 'react';
import {
  DualDomainMeteringCockpitProps,
  MeteringDomainType,
} from './dualDomainMeteringTypes';

function getDomainBadge(domain: MeteringDomainType): { label: string; className: string } {
  if (domain === 'gateway_domain') {
    return {
      label: '网关域 (Gateway)',
      className: 'bg-indigo-950 text-indigo-300 border-indigo-700/80',
    };
  }
  return {
    label: '沙箱域 (Sandbox)',
    className: 'bg-emerald-950 text-emerald-300 border-emerald-700/80',
  };
}

export const DualDomainMeteringCockpit: React.FC<DualDomainMeteringCockpitProps> = ({
  summary,
  records,
  statement,
  onGenerateStatement,
  onRefresh,
  isRefreshing = false,
}) => {
  const [filterDomain, setFilterDomain] = useState<'all' | MeteringDomainType>('all');
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [copiedHash, setCopiedHash] = useState<boolean>(false);

  const filteredRecords = records.filter((r) => {
    if (filterDomain === 'all') return true;
    return r.domain === filterDomain;
  });

  const handleGenerate = async () => {
    if (!onGenerateStatement) return;
    setIsGenerating(true);
    try {
      await onGenerateStatement(summary.session_id);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleCopyHash = (hash: string) => {
    navigator.clipboard.writeText(hash);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 2000);
  };

  return (
    <div className="flex flex-col h-full bg-slate-950 text-slate-100 rounded-xl border border-slate-800 shadow-2xl overflow-hidden">
      {/* Header & Dual-Domain Boundary Declaration Banner */}
      <div className="px-6 py-4 border-b border-slate-800 bg-slate-900/90 space-y-2.5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <span className="text-emerald-400">⚖️</span> 双域透明计量边界与三维穿透成本驾驶舱
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              严格界定【管控网关域】与【沙箱执行域】计量边界，三维穿透核算 Token、容器算力与第三方工具增值开销
            </p>
          </div>

          <div className="flex items-center gap-2">
            {onGenerateStatement && (
              <button
                onClick={handleGenerate}
                disabled={isGenerating}
                className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-500/30 transition-colors disabled:opacity-50"
              >
                {isGenerating ? '签署中...' : '生成合规对账单'}
              </button>
            )}

            {onRefresh && (
              <button
                onClick={onRefresh}
                disabled={isRefreshing}
                className="p-1.5 text-xs bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-slate-300 transition-colors"
                title="刷新账本"
              >
                🔄
              </button>
            )}
          </div>
        </div>

        {/* Dual-Domain Transparency Policy Pill */}
        <div className="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800/80 flex flex-wrap items-center justify-between text-xs gap-3">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5 font-medium text-indigo-300">
              <span className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse" />
              网关域 (Gateway): 按 Token 精确计量
            </span>
            <span className="text-slate-600">|</span>
            <span className="flex items-center gap-1.5 font-medium text-emerald-300">
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              沙箱域 (Sandbox): 按容器算力租约/本地免计费
            </span>
          </div>
          <span className="text-[11px] text-slate-400 font-mono">
            会话 ID: {summary.session_id}
          </span>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 min-h-0 overflow-y-auto p-5 space-y-5 bg-slate-950">
        {/* 3D Penetrating Cost Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3.5">
          {/* Card 1: Total Cost */}
          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
            <div className="text-xs text-slate-400 font-medium">总穿透核算成本</div>
            <div className="text-xl font-bold text-white font-mono">
              ${summary.total_cost_usd.toFixed(4)}
            </div>
            <div className="text-[11px] text-slate-400">
              共计 {summary.total_operations} 次计量调用
            </div>
          </div>

          {/* Card 2: Model Token Cost */}
          <div className="p-4 rounded-xl bg-indigo-950/20 border border-indigo-800/40 space-y-1">
            <div className="text-xs text-indigo-300 font-medium">大模型 Token 成本</div>
            <div className="text-xl font-bold text-indigo-200 font-mono">
              ${summary.gateway_token_cost_usd.toFixed(4)}
            </div>
            <div className="text-[11px] text-indigo-400/80">
              网关调用 {summary.gateway_ops_count} 次 ({(summary.gateway_cost_ratio * 100).toFixed(1)}%)
            </div>
          </div>

          {/* Card 3: Sandbox Compute Cost */}
          <div className="p-4 rounded-xl bg-emerald-950/20 border border-emerald-800/40 space-y-1">
            <div className="text-xs text-emerald-300 font-medium">沙箱容器算力成本</div>
            <div className="text-xl font-bold text-emerald-200 font-mono">
              ${summary.sandbox_compute_cost_usd.toFixed(4)}
            </div>
            <div className="text-[11px] text-emerald-400/80">
              沙箱运行 {summary.sandbox_ops_count} 次
            </div>
          </div>

          {/* Card 4: Third-Party MCP / API Surcharges */}
          <div className="p-4 rounded-xl bg-cyan-950/20 border border-cyan-800/40 space-y-1">
            <div className="text-xs text-cyan-300 font-medium">外部增值与 MCP 成本</div>
            <div className="text-xl font-bold text-cyan-200 font-mono">
              ${summary.thirdparty_tool_cost_usd.toFixed(4)}
            </div>
            <div className="text-[11px] text-cyan-400/80">
              三方服务增值计费
            </div>
          </div>
        </div>

        {/* Domain Cost Split Ratio Bar */}
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="font-semibold text-slate-300">双域成本分摊比例</span>
            <div className="flex items-center gap-3 font-mono text-[11px]">
              <span className="text-indigo-300">
                网关域: {(summary.gateway_cost_ratio * 100).toFixed(1)}%
              </span>
              <span className="text-emerald-300">
                沙箱域: {(summary.sandbox_cost_ratio * 100).toFixed(1)}%
              </span>
            </div>
          </div>
          <div className="w-full h-2.5 rounded-full bg-slate-800 overflow-hidden flex">
            <div
              className="bg-indigo-500 h-full transition-all"
              style={{ width: `${Math.round(summary.gateway_cost_ratio * 100)}%` }}
            />
            <div
              className="bg-emerald-500 h-full transition-all"
              style={{ width: `${Math.round(summary.sandbox_cost_ratio * 100)}%` }}
            />
          </div>
        </div>

        {/* Cryptographically Sealed Statement Banner (if generated) */}
        {statement && (
          <div className="p-4 rounded-xl bg-slate-900/90 border border-emerald-600/50 space-y-2 shadow-lg">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-emerald-300 flex items-center gap-1.5">
                <span>🔐</span> 企业财务合规对账凭据已签署 (Tamper-Proof Audit Statement)
              </span>
              <span className="text-[10px] text-slate-400 font-mono">
                单号: {statement.statement_id}
              </span>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono">
              <span className="text-slate-400 truncate max-w-lg">
                SHA-256: {statement.integrity_sha256}
              </span>
              <button
                onClick={() => handleCopyHash(statement.integrity_sha256)}
                className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px] transition-colors"
              >
                {copiedHash ? '已复制' : '复制哈希'}
              </button>
            </div>
          </div>
        )}

        {/* Filter Bar & Detailed Records Table */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
              计量流水明细 ({filteredRecords.length})
            </span>

            <div className="flex items-center gap-1 p-1 rounded-lg bg-slate-900 border border-slate-800 text-xs">
              <button
                onClick={() => setFilterDomain('all')}
                className={`px-2.5 py-1 rounded text-xs transition-colors ${
                  filterDomain === 'all' ? 'bg-slate-800 text-white font-medium' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                全部
              </button>
              <button
                onClick={() => setFilterDomain('gateway_domain')}
                className={`px-2.5 py-1 rounded text-xs transition-colors ${
                  filterDomain === 'gateway_domain'
                    ? 'bg-indigo-900/60 text-indigo-300 font-medium'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                网关域
              </button>
              <button
                onClick={() => setFilterDomain('sandbox_domain')}
                className={`px-2.5 py-1 rounded text-xs transition-colors ${
                  filterDomain === 'sandbox_domain'
                    ? 'bg-emerald-900/60 text-emerald-300 font-medium'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                沙箱域
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-slate-800 overflow-hidden bg-slate-900/40">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-900/80 text-slate-400 font-semibold border-b border-slate-800">
                <tr>
                  <th className="px-4 py-2.5">记录 ID</th>
                  <th className="px-4 py-2.5">计量域</th>
                  <th className="px-4 py-2.5">操作类型</th>
                  <th className="px-4 py-2.5">资源用量</th>
                  <th className="px-4 py-2.5">三维折算成本</th>
                  <th className="px-4 py-2.5">计费政策说明</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-300 font-mono">
                {filteredRecords.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="text-center py-8 text-slate-500 font-sans">
                      暂无计量流水记录
                    </td>
                  </tr>
                ) : (
                  filteredRecords.map((r) => {
                    const badge = getDomainBadge(r.domain);
                    return (
                      <tr key={r.record_id} className="hover:bg-slate-850/60 transition-colors">
                        <td className="px-4 py-2.5 text-slate-400 text-[11px]">{r.record_id}</td>
                        <td className="px-4 py-2.5">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-sans border ${badge.className}`}>
                            {badge.label}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 font-sans font-medium text-slate-200">{r.operation_name}</td>
                        <td className="px-4 py-2.5 text-[11px]">{r.resource_units}</td>
                        <td className="px-4 py-2.5 font-bold text-amber-300">${r.cost_breakdown.total_cost_usd.toFixed(4)}</td>
                        <td className="px-4 py-2.5 font-sans text-slate-400 text-[11px]">{r.policy_note || '标准计量政策'}</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
