/**
 * [INPUT]: Cross-period pivot report, user gamified profile, and team adoption insights.
 * [OUTPUT]: High-performance dashboard deck with cross-period comparisons, per-agent breakdowns, and gamified milestones.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/MultiAgentCrossPeriodPivotDeck.tsx
 */

import React, { useState } from 'react';
import {
  MultiAgentCrossPeriodPivotDeckProps,
  PeriodType,
} from './crossPeriodMilestoneTypes';

export const MultiAgentCrossPeriodPivotDeck: React.FC<MultiAgentCrossPeriodPivotDeckProps> = ({
  report,
  profile,
  teamInsights,
  onPeriodChange,
  onClaimTask,
  onRefresh,
  isRefreshing = false,
}) => {
  const [activeTab, setActiveTab] = useState<'pivot' | 'gamification' | 'team'>('pivot');
  const [claimingTaskId, setClaimingTaskId] = useState<string | null>(null);

  const handlePeriodClick = (p: PeriodType) => {
    if (onPeriodChange) {
      onPeriodChange(p);
    }
  };

  const handleClaim = async (taskId: string) => {
    if (!onClaimTask) return;
    try {
      setClaimingTaskId(taskId);
      await onClaimTask(taskId);
    } finally {
      setClaimingTaskId(null);
    }
  };

  const current = report.current_period;
  const prev = report.previous_period;

  const xpPercent = Math.min(
    100,
    Math.round((profile.current_xp / Math.max(profile.next_level_xp, 1)) * 100)
  );

  return (
    <div
      data-testid="multi-agent-cross-period-pivot-deck"
      className="p-5 bg-neutral-900 border border-neutral-800 rounded-xl text-neutral-100 shadow-xl space-y-6"
    >
      {/* 顶部标题与控制栏 */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-neutral-800 pb-4">
        <div>
          <div className="flex items-center gap-3">
            <span className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              <span className="text-indigo-400">📊</span> 多智能体跨周期透视与人效里程碑
            </span>
            <span className="px-2.5 py-0.5 text-xs font-semibold rounded-full bg-indigo-900/60 text-indigo-300 border border-indigo-700/60">
              {current.period_label}
            </span>
          </div>
          <p className="text-xs text-neutral-400 mt-1">
            运行时用量跨周期透视对比 · 相对上期环比 · 游戏化成长体系与团队拥抱度洞察
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* 周期切换 Pills */}
          <div className="flex bg-neutral-800 p-1 rounded-lg border border-neutral-700">
            {(['weekly', 'monthly', 'quarterly'] as PeriodType[]).map((p) => {
              const isActive = current.period_type === p;
              const labelMap: Record<string, string> = {
                weekly: '周报',
                monthly: '月报',
                quarterly: '季度报',
              };
              return (
                <button
                  key={p}
                  type="button"
                  data-testid={`period-pill-${p}`}
                  onClick={() => handlePeriodClick(p)}
                  className={`px-3 py-1 text-xs font-medium rounded-md transition-all ${
                    isActive
                      ? 'bg-indigo-600 text-white shadow-sm font-semibold'
                      : 'text-neutral-400 hover:text-neutral-200'
                  }`}
                >
                  {labelMap[p]}
                </button>
              );
            })}
          </div>

          {onRefresh && (
            <button
              type="button"
              data-testid="btn-refresh-pivot"
              onClick={onRefresh}
              disabled={isRefreshing}
              className="px-3 py-1.5 text-xs bg-neutral-800 hover:bg-neutral-700 text-neutral-300 border border-neutral-700 rounded-lg transition"
            >
              {isRefreshing ? '刷新中...' : '刷新'}
            </button>
          )}
        </div>
      </div>

      {/* 视图切换 Tab */}
      <div className="flex border-b border-neutral-800 gap-6 text-sm">
        <button
          type="button"
          data-testid="tab-pivot"
          onClick={() => setActiveTab('pivot')}
          className={`pb-2.5 font-medium transition border-b-2 ${
            activeTab === 'pivot'
              ? 'border-indigo-500 text-indigo-400 font-semibold'
              : 'border-transparent text-neutral-400 hover:text-neutral-200'
          }`}
        >
          📈 周期透视报表 ({current.agent_breakdowns.length} 个智能体)
        </button>
        <button
          type="button"
          data-testid="tab-gamification"
          onClick={() => setActiveTab('gamification')}
          className={`pb-2.5 font-medium transition border-b-2 ${
            activeTab === 'gamification'
              ? 'border-indigo-500 text-indigo-400 font-semibold'
              : 'border-transparent text-neutral-400 hover:text-neutral-200'
          }`}
        >
          🏆 人效进阶体系 (Lv.{profile.level} · {profile.rank_title})
        </button>
        <button
          type="button"
          data-testid="tab-team"
          onClick={() => setActiveTab('team')}
          className={`pb-2.5 font-medium transition border-b-2 ${
            activeTab === 'team'
              ? 'border-indigo-500 text-indigo-400 font-semibold'
              : 'border-transparent text-neutral-400 hover:text-neutral-200'
          }`}
        >
          👥 团队拥抱度榜单 ({teamInsights.total_active_members} 人)
        </button>
      </div>

      {/* TAB 1: 周期透视报表 */}
      {activeTab === 'pivot' && (
        <div className="space-y-6">
          {/* KPI 关键指标卡片 */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {/* Token 用量 */}
            <div className="bg-neutral-800/70 p-4 rounded-xl border border-neutral-700/60">
              <div className="text-xs text-neutral-400">总 Token 消耗</div>
              <div className="text-2xl font-bold text-white mt-1">
                {current.total_tokens.toLocaleString()}
              </div>
              <div className="mt-2 text-xs flex items-center gap-1.5">
                {report.token_growth_pct !== null && report.token_growth_pct !== undefined ? (
                  <span
                    className={`font-semibold ${
                      report.token_growth_pct > 0 ? 'text-amber-400' : 'text-emerald-400'
                    }`}
                  >
                    {report.token_growth_pct > 0 ? '▲' : '▼'} {Math.abs(report.token_growth_pct)}%
                  </span>
                ) : (
                  <span className="text-neutral-500">上期无基准数据</span>
                )}
                <span className="text-neutral-400">相对上一等长周期</span>
              </div>
            </div>

            {/* 累计费用 */}
            <div className="bg-neutral-800/70 p-4 rounded-xl border border-neutral-700/60">
              <div className="text-xs text-neutral-400">周期核算费用 (USD)</div>
              <div className="text-2xl font-bold text-emerald-400 mt-1">
                ${current.total_cost_usd.toFixed(4)}
              </div>
              <div className="mt-2 text-xs flex items-center gap-1.5">
                {report.cost_growth_pct !== null && report.cost_growth_pct !== undefined ? (
                  <span
                    className={`font-semibold ${
                      report.cost_growth_pct > 0 ? 'text-amber-400' : 'text-emerald-400'
                    }`}
                  >
                    {report.cost_growth_pct > 0 ? '▲' : '▼'} {Math.abs(report.cost_growth_pct)}%
                  </span>
                ) : (
                  <span className="text-neutral-500">上期无基准数据</span>
                )}
                <span className="text-neutral-400">相对上一等长周期</span>
              </div>
            </div>

            {/* 总任务调用 */}
            <div className="bg-neutral-800/70 p-4 rounded-xl border border-neutral-700/60">
              <div className="text-xs text-neutral-400">任务执行次数</div>
              <div className="text-2xl font-bold text-indigo-300 mt-1">
                {current.total_invocations} 次
              </div>
              <div className="mt-2 text-xs flex items-center gap-1.5">
                {report.invocation_growth_pct !== null && report.invocation_growth_pct !== undefined ? (
                  <span
                    className={`font-semibold ${
                      report.invocation_growth_pct >= 0 ? 'text-indigo-400' : 'text-neutral-400'
                    }`}
                  >
                    {report.invocation_growth_pct >= 0 ? '▲' : '▼'} {Math.abs(report.invocation_growth_pct)}%
                  </span>
                ) : (
                  <span className="text-neutral-500">上期无基准数据</span>
                )}
                <span className="text-neutral-400">执行频次环比</span>
              </div>
            </div>
          </div>

          {/* 智能体运行时拆分横向堆叠表 */}
          <div className="bg-neutral-800/40 rounded-xl border border-neutral-700/60 overflow-hidden">
            <div className="p-3 bg-neutral-800/80 border-b border-neutral-700/60 text-xs font-semibold text-neutral-300">
              各智能体运行时消耗透视拆分 ({current.start_date} ~ {current.end_date})
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-neutral-300">
                <thead className="bg-neutral-800/60 text-neutral-400 border-b border-neutral-700/40">
                  <tr>
                    <th className="py-2.5 px-3">智能体名称</th>
                    <th className="py-2.5 px-3">Token 占比</th>
                    <th className="py-2.5 px-3">Input / Output</th>
                    <th className="py-2.5 px-3">费用 USD</th>
                    <th className="py-2.5 px-3">调用次数</th>
                    <th className="py-2.5 px-3">成功率</th>
                    <th className="py-2.5 px-3">平均延迟</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-800">
                  {current.agent_breakdowns.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="py-6 text-center text-neutral-500">
                        当前周期暂无智能体调用记录
                      </td>
                    </tr>
                  ) : (
                    current.agent_breakdowns.map((ag) => (
                      <tr key={ag.agent_id} className="hover:bg-neutral-800/50 transition">
                        <td className="py-2.5 px-3 font-medium text-white flex items-center gap-2">
                          <span className="w-2 h-2 rounded-full bg-indigo-400"></span>
                          {ag.agent_name}
                        </td>
                        <td className="py-2.5 px-3">
                          <div className="flex items-center gap-2">
                            <div className="w-20 bg-neutral-700 rounded-full h-1.5 overflow-hidden">
                              <div
                                className="bg-indigo-500 h-1.5 rounded-full"
                                style={{ width: `${Math.min(ag.token_share_pct, 100)}%` }}
                              ></div>
                            </div>
                            <span className="font-semibold text-indigo-300">{ag.token_share_pct}%</span>
                          </div>
                        </td>
                        <td className="py-2.5 px-3 text-neutral-400">
                          {ag.tokens_in.toLocaleString()} / {ag.tokens_out.toLocaleString()}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-emerald-400">
                          ${ag.cost_usd.toFixed(4)}
                        </td>
                        <td className="py-2.5 px-3">{ag.invocation_count}</td>
                        <td className="py-2.5 px-3">
                          <span
                            className={`px-2 py-0.5 rounded-md font-semibold ${
                              ag.success_rate >= 0.95
                                ? 'bg-emerald-950/70 text-emerald-300 border border-emerald-800/60'
                                : 'bg-amber-950/70 text-amber-300 border border-amber-800/60'
                            }`}
                          >
                            {(ag.success_rate * 100).toFixed(0)}%
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-neutral-400">{ag.avg_latency_ms} ms</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: 人效进阶与游戏化成长体系 */}
      {activeTab === 'gamification' && (
        <div className="space-y-6">
          {/* 用户等级与经验条 */}
          <div className="bg-gradient-to-r from-neutral-800 via-neutral-800/80 to-indigo-950/40 p-5 rounded-xl border border-indigo-900/50 flex flex-wrap items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-3">
                <span className="text-2xl font-black text-amber-400">Lv.{profile.level}</span>
                <span className="text-lg font-bold text-white">{profile.rank_title}</span>
                <span className="px-2.5 py-0.5 text-xs bg-amber-950/80 text-amber-300 border border-amber-700/60 rounded-full font-medium">
                  🔥 连续协同 {profile.streak_days} 天
                </span>
              </div>
              <div className="text-xs text-neutral-400">
                协同员工: {profile.user_name} · 累计产出经验 {profile.total_xp} XP
              </div>
            </div>

            <div className="w-full sm:w-72 space-y-1.5">
              <div className="flex justify-between text-xs text-neutral-300 font-medium">
                <span>经验值进度</span>
                <span>
                  {profile.current_xp} / {profile.next_level_xp} XP
                </span>
              </div>
              <div className="w-full bg-neutral-700 rounded-full h-2.5 overflow-hidden">
                <div
                  className="bg-gradient-to-r from-amber-500 to-indigo-500 h-2.5 rounded-full transition-all duration-300"
                  style={{ width: `${xpPercent}%` }}
                ></div>
              </div>
            </div>
          </div>

          {/* 每日人效打卡任务 */}
          <div className="space-y-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
              🎯 今日日常协同任务
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {profile.daily_tasks.map((task) => (
                <div
                  key={task.id}
                  className={`p-4 rounded-xl border transition flex flex-col justify-between gap-3 ${
                    task.is_completed
                      ? 'bg-neutral-800/30 border-neutral-700/40 opacity-80'
                      : 'bg-neutral-800/80 border-neutral-700 hover:border-indigo-500/50'
                  }`}
                >
                  <div>
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-sm text-white">{task.title}</span>
                      <span className="text-xs px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800 font-bold">
                        +{task.xp_reward} XP
                      </span>
                    </div>
                    <p className="text-xs text-neutral-400 mt-2 leading-relaxed">
                      {task.description}
                    </p>
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-neutral-700/40">
                    <span className="text-xs text-neutral-400 font-medium">
                      进度: {task.progress}/{task.max_progress}
                    </span>
                    {task.is_completed ? (
                      <span className="text-xs font-semibold text-emerald-400 flex items-center gap-1">
                        ✓ 已完成
                      </span>
                    ) : (
                      <button
                        type="button"
                        data-testid={`claim-task-${task.id}`}
                        onClick={() => handleClaim(task.id)}
                        disabled={claimingTaskId === task.id}
                        className="px-2.5 py-1 text-xs bg-indigo-600 hover:bg-indigo-500 text-white rounded font-medium transition"
                      >
                        {claimingTaskId === task.id ? '打卡中...' : '一键打卡'}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 效率进阶勋章墙 */}
          <div className="space-y-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
              🏅 人效进阶勋章墙
            </h4>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {profile.badges.map((badge) => {
                const tierBorder: Record<string, string> = {
                  bronze: 'border-amber-700/50 bg-amber-950/20',
                  silver: 'border-slate-500/50 bg-slate-900/40',
                  gold: 'border-yellow-500/50 bg-yellow-950/30',
                  platinum: 'border-cyan-500/50 bg-cyan-950/30',
                };
                return (
                  <div
                    key={badge.id}
                    className={`p-3.5 rounded-xl border text-center transition space-y-1.5 ${
                      badge.is_unlocked
                        ? `${tierBorder[badge.tier]} shadow-md`
                        : 'border-neutral-800 bg-neutral-850 opacity-40'
                    }`}
                  >
                    <div className="text-2xl">{badge.is_unlocked ? '🎖️' : '🔒'}</div>
                    <div className="font-bold text-xs text-white">{badge.name}</div>
                    <div className="text-[11px] text-neutral-400 leading-tight">
                      {badge.description}
                    </div>
                    {badge.is_unlocked && (
                      <div className="text-[10px] text-emerald-400 font-semibold pt-1">
                        ✓ 已解锁
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: 团队拥抱度与活跃榜单 */}
      {activeTab === 'team' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-neutral-800/70 p-4 rounded-xl border border-neutral-700/60">
              <div className="text-xs text-neutral-400">团队活跃协同成员</div>
              <div className="text-2xl font-bold text-white mt-1">
                {teamInsights.total_active_members} 人
              </div>
            </div>
            <div className="bg-neutral-800/70 p-4 rounded-xl border border-neutral-700/60">
              <div className="text-xs text-neutral-400">平均连续活跃天数</div>
              <div className="text-2xl font-bold text-amber-400 mt-1">
                {teamInsights.average_streak_days} 天
              </div>
            </div>
            <div className="bg-neutral-800/70 p-4 rounded-xl border border-neutral-700/60">
              <div className="text-xs text-neutral-400">全员协同任务总会话</div>
              <div className="text-2xl font-bold text-indigo-400 mt-1">
                {teamInsights.total_team_sessions} 次
              </div>
            </div>
          </div>

          {/* 团队排行榜表格 */}
          <div className="bg-neutral-800/40 rounded-xl border border-neutral-700/60 overflow-hidden">
            <div className="p-3 bg-neutral-800/80 border-b border-neutral-700/60 text-xs font-semibold text-neutral-300">
              团队 AI 生产力与连续协同活跃度排行榜
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-neutral-300">
                <thead className="bg-neutral-800/60 text-neutral-400 border-b border-neutral-700/40">
                  <tr>
                    <th className="py-2.5 px-3">排名</th>
                    <th className="py-2.5 px-3">协同成员</th>
                    <th className="py-2.5 px-3">所属部门</th>
                    <th className="py-2.5 px-3">等级与头衔</th>
                    <th className="py-2.5 px-3">连续活跃</th>
                    <th className="py-2.5 px-3">会话数</th>
                    <th className="py-2.5 px-3">Token 用量</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-800">
                  {teamInsights.leaderboard.map((m, idx) => (
                    <tr key={m.user_id} className="hover:bg-neutral-800/50 transition">
                      <td className="py-2.5 px-3 font-bold text-amber-400">#{idx + 1}</td>
                      <td className="py-2.5 px-3 font-semibold text-white">{m.user_name}</td>
                      <td className="py-2.5 px-3 text-neutral-400">{m.department}</td>
                      <td className="py-2.5 px-3">
                        <span className="text-indigo-300 font-medium">
                          Lv.{m.level} {m.rank_title}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 font-semibold text-amber-300">
                        🔥 {m.streak_days} 天
                      </td>
                      <td className="py-2.5 px-3">{m.sessions_count}</td>
                      <td className="py-2.5 px-3 font-mono text-emerald-400">
                        {m.total_tokens.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
