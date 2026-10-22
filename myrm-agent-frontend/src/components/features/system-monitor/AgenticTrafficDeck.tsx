/**
 * [INPUT]
 * - summary: AgentTrafficSummaryData | null 流量统计全景数据
 * - onRefresh?: () => void 刷新流量看板回调
 * - loading?: boolean 加载状态
 *
 * [OUTPUT]
 * - AgenticTrafficDeck: AI Agent 流量精准解构与 4 阶梯转化漏斗全景看板
 *
 * [POS]
 * src/components/features/system-monitor/AgenticTrafficDeck.tsx — AI Agent 流量大盘与转化漏斗组件
 */

import React from 'react';
import type { AgentTrafficSummaryData } from './agenticTrafficTypes';

export interface AgenticTrafficDeckProps {
  summary: AgentTrafficSummaryData | null;
  onRefresh?: () => void;
  loading?: boolean;
  className?: string;
}

const AGENT_BADGE_STYLE: Record<string, string> = {
  CURSOR: 'bg-indigo-950/60 text-indigo-300 border-indigo-700/60',
  CLAUDE_CODE: 'bg-amber-950/60 text-amber-300 border-amber-700/60',
  WINDSURF: 'bg-teal-950/60 text-teal-300 border-teal-700/60',
  AIDER: 'bg-emerald-950/60 text-emerald-300 border-emerald-700/60',
  CLINE: 'bg-sky-950/60 text-sky-300 border-sky-700/60',
  OPENCLAW: 'bg-purple-950/60 text-purple-300 border-purple-700/60',
  MYRM: 'bg-rose-950/60 text-rose-300 border-rose-700/60',
};

const FUNNEL_LABELS: Record<string, { label: string; desc: string }> = {
  DISCOVERED: { label: '① 触达检索', desc: 'Agent 到访抓取文档或首页' },
  CONTEXT_ABSORBED: { label: '② 上下文吸收', desc: '首屏 500 Token 示例被成功理解' },
  SANDBOX_PROBED: { label: '③ 沙箱/API 试调', desc: '发起探针或接口语法验证' },
  ADOPTED: { label: '④ 正式采纳集成', desc: '形成业务代码集成与长期调用' },
};

export const AgenticTrafficDeck: React.FC<AgenticTrafficDeckProps> = ({
  summary,
  onRefresh,
  loading = false,
  className = '',
}) => {
  if (!summary) {
    return (
      <div
        data-testid="agentic-traffic-loading"
        className={`p-5 rounded-xl border border-slate-800 bg-slate-900/80 text-slate-400 flex items-center space-x-3 ${className}`}
      >
        <div className="w-4 h-4 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
        <span className="text-xs">正在分析 AI Agent 流量特征与转化漏斗...</span>
      </div>
    );
  }

  const {
    total_visits,
    agent_visits_count,
    human_visits_count,
    agent_traffic_ratio_pct,
    top_agents,
    funnel_conversion,
    recent_visits,
  } = summary;

  return (
    <div
      data-testid="agentic-traffic-deck"
      className={`p-5 rounded-xl border border-slate-800 bg-slate-900/90 space-y-5 ${className}`}
    >
      {/* 头部标题与控制栏 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-800/80">
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center font-bold text-sm">
            🤖
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="text-sm font-semibold text-slate-100">
                AI Agent 专属流量解构与转化漏斗
              </h3>
              <span
                data-testid="agent-ratio-badge"
                className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-indigo-950/60 text-indigo-300 border border-indigo-700/60"
              >
                AI 流量占比 {agent_traffic_ratio_pct}%
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              深度区分 Coding Agent 静默审判与普通浏览器流量，打破传统分析 100% 跳出失明
            </p>
          </div>
        </div>

        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={loading}
            data-testid="refresh-traffic-btn"
            className="px-3 py-1.5 text-xs font-medium text-slate-200 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 rounded-lg border border-slate-700 transition self-end sm:self-center"
          >
            {loading ? '刷新中...' : '刷新流量看板'}
          </button>
        )}
      </div>

      {/* 核心流量指标卡片 */}
      <div className="grid grid-cols-3 gap-3">
        <div className="p-3 bg-slate-800/40 rounded-lg border border-slate-700/50 space-y-1">
          <div className="text-[11px] text-slate-400">总访问量 (Inbound)</div>
          <div className="text-base font-bold font-mono text-slate-100">
            {total_visits.toLocaleString()}
          </div>
          <div className="text-[10px] text-slate-400">全站请求时序统计</div>
        </div>

        <div className="p-3 bg-slate-800/40 rounded-lg border border-slate-700/50 space-y-1">
          <div className="text-[11px] text-slate-400">AI Coding Agent</div>
          <div className="text-base font-bold font-mono text-indigo-400">
            {agent_visits_count.toLocaleString()}
          </div>
          <div className="text-[10px] text-indigo-300/80">占比 {agent_traffic_ratio_pct}%</div>
        </div>

        <div className="p-3 bg-slate-800/40 rounded-lg border border-slate-700/50 space-y-1">
          <div className="text-[11px] text-slate-400">普通人类浏览器</div>
          <div className="text-base font-bold font-mono text-slate-200">
            {human_visits_count.toLocaleString()}
          </div>
          <div className="text-[10px] text-slate-400">含鼠标移动与完整渲染</div>
        </div>
      </div>

      {/* 主流 Agent 占比分布卡片 */}
      <div className="space-y-2">
        <h4 className="text-xs font-semibold text-slate-300">活跃 Coding Agent 分布</h4>
        <div className="flex flex-wrap gap-2" data-testid="agent-badges-list">
          {Object.entries(top_agents).map(([agent, count]) => {
            const badgeCls = AGENT_BADGE_STYLE[agent] || 'bg-slate-800 text-slate-300 border-slate-700';
            return (
              <span
                key={agent}
                data-testid={`badge-${agent}`}
                className={`px-2.5 py-1 rounded-lg border text-xs font-medium flex items-center space-x-1.5 ${badgeCls}`}
              >
                <span>{agent}</span>
                <span className="font-mono font-bold bg-black/20 px-1 rounded text-[11px]">{count}</span>
              </span>
            );
          })}
        </div>
      </div>

      {/* 4 阶梯转化漏斗 */}
      <div className="space-y-2">
        <h4 className="text-xs font-semibold text-slate-300">AI 时代转化漏斗 (4-Stage Funnel)</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5" data-testid="funnel-grid">
          {Object.entries(FUNNEL_LABELS).map(([stageKey, meta]) => {
            const count = funnel_conversion[stageKey] || 0;
            return (
              <div
                key={stageKey}
                data-testid={`funnel-step-${stageKey}`}
                className="p-3 bg-slate-850 rounded-lg border border-slate-800 hover:border-slate-700 transition space-y-1"
              >
                <div className="text-xs font-semibold text-slate-200">{meta.label}</div>
                <div className="text-lg font-bold font-mono text-indigo-400">{count}</div>
                <div className="text-[10px] text-slate-400">{meta.desc}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 最近 Agent 访问流水快照 */}
      {recent_visits.length > 0 && (
        <div className="space-y-2 pt-2 border-t border-slate-800/60">
          <h4 className="text-xs font-semibold text-slate-300">最近 Agent 审判流水快照</h4>
          <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1" data-testid="recent-visits-list">
            {recent_visits.slice(0, 5).map((v) => (
              <div
                key={v.visit_id}
                data-testid={`visit-item-${v.visit_id}`}
                className="p-2 rounded bg-slate-950/60 border border-slate-800/80 flex items-center justify-between text-xs"
              >
                <div className="flex items-center space-x-2">
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] font-mono border ${
                      v.is_agent ? 'bg-indigo-950/80 text-indigo-300 border-indigo-700/60' : 'bg-slate-800 text-slate-400 border-slate-700'
                    }`}
                  >
                    {v.agent_type}
                  </span>
                  <span className="font-mono text-slate-300">{v.target_path}</span>
                </div>
                <div className="flex items-center space-x-3 text-[11px] text-slate-400 font-mono">
                  <span>{v.duration_ms.toFixed(0)}ms</span>
                  <span className="text-indigo-400">{v.funnel_stage}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
