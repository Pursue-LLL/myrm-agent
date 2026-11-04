import React from 'react';
import {
  TrendingUp,
  ShieldCheck,
  Clock,
  Ban,
  Activity,
} from 'lucide-react';
import { useTeamRuntimeStore } from './useTeamRuntimeStore';

export const CoordinationReductionCard: React.FC = () => {
  const { telemetry } = useTeamRuntimeStore();

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4 shadow-xl backdrop-blur-md">
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div className="flex items-center space-x-2">
          <Activity className="h-4 w-4 text-emerald-400" />
          <h3 className="text-xs font-semibold text-slate-100">
            数字团队协同减负度量大盘
          </h3>
          <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-400">
            Coordination Telemetry
          </span>
        </div>
        <div className="flex items-center space-x-1.5 text-xs text-slate-400">
          <span>协同健康度:</span>
          <span className="font-mono font-bold text-emerald-400">
            {telemetry.coordinationHealthScore} / 100
          </span>
        </div>
      </div>

      <div className="mt-3.5 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-lg border border-slate-800 bg-slate-850/80 p-3">
          <div className="flex items-center space-x-2 text-slate-400">
            <ShieldCheck className="h-4 w-4 text-blue-400" />
            <span className="text-[11px]">避免人工口径纠偏</span>
          </div>
          <div className="mt-2 flex items-baseline space-x-1">
            <span className="text-xl font-bold text-slate-100 font-mono">
              {telemetry.preventedAlignmentsCount}
            </span>
            <span className="text-xs text-slate-400">次</span>
          </div>
          <p className="mt-1 text-[10px] text-slate-500">
            通过契约已决事实锁死跨 Agent 认知歧义
          </p>
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-850/80 p-3">
          <div className="flex items-center space-x-2 text-slate-400">
            <Clock className="h-4 w-4 text-amber-400" />
            <span className="text-[11px]">节省人工对账时间</span>
          </div>
          <div className="mt-2 flex items-baseline space-x-1">
            <span className="text-xl font-bold text-slate-100 font-mono">
              {telemetry.savedManualMinutes}
            </span>
            <span className="text-xs text-slate-400">分钟</span>
          </div>
          <p className="mt-1 text-[10px] text-slate-500">
            彻底终结用户充当“隐形第四人”线下反复拉齐
          </p>
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-850/80 p-3">
          <div className="flex items-center space-x-2 text-slate-400">
            <Ban className="h-4 w-4 text-purple-400" />
            <span className="text-[11px]">阻断下游无效盲跑</span>
          </div>
          <div className="mt-2 flex items-baseline space-x-1">
            <span className="text-xl font-bold text-slate-100 font-mono">
              {telemetry.blockedBlindRerunsCount}
            </span>
            <span className="text-xs text-slate-400">个任务</span>
          </div>
          <p className="mt-1 text-[10px] text-slate-500">
            上游前提变更时自动拦截下游并标明原因
          </p>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-slate-800/80 pt-2 text-[10px] text-slate-500">
        <span className="flex items-center space-x-1">
          <TrendingUp className="h-3 w-3 text-emerald-400" />
          <span>相比单 Agent 自由群聊，有效消除 90% 以上黑盒扯皮与口径不一致</span>
        </span>
        <span className="font-mono text-slate-400">指标随拓扑状态实时反应式更新</span>
      </div>
    </div>
  );
};
