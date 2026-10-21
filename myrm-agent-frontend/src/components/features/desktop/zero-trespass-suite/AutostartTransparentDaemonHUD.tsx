import React from 'react';
import {
  Activity,
  CheckCircle2,
  Cpu,
  PowerOff,
  Radio,
  Server,
  ShieldCheck,
  ShieldX,
  Trash2,
} from 'lucide-react';
import { useZeroTrespassStore } from './useZeroTrespassStore';

interface AutostartTransparentDaemonHUDProps {
  className?: string;
}

export const AutostartTransparentDaemonHUD: React.FC<AutostartTransparentDaemonHUDProps> = ({
  className = '',
}) => {
  const {
    autostartAuth,
    daemonMetrics,
    setAutostartAuth,
    killAndCleanZombieProcess,
  } = useZeroTrespassStore();

  const isAutostartEnabled = autostartAuth === 'granted';

  return (
    <section
      aria-label="零越界自启动与常驻后台透明监控看板"
      className={`rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow-sm backdrop-blur ${className}`}
    >
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <ShieldCheck className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-100">零越界自启动契约与后台常驻透明看板</h3>
            <p className="text-[11px] text-slate-400">
              单向不可逆授权守卫 · 绝不擅自添加开机启动项或 4 小时后台保活任务
            </p>
          </div>
        </div>

        {/* 自启动不可逆授权开关 */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">
            {isAutostartEnabled ? '已显式授权开机自启' : '开机自启已禁用 (系统保护)'}
          </span>
          <button
            type="button"
            onClick={() => {
              setAutostartAuth(isAutostartEnabled ? 'denied' : 'granted');
            }}
            className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
              isAutostartEnabled ? 'bg-indigo-600' : 'bg-slate-700'
            }`}
            aria-label={isAutostartEnabled ? '关闭开机自启动' : '开启开机自启动'}
          >
            <span
              className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                isAutostartEnabled ? 'translate-x-4' : 'translate-x-0'
              }`}
            />
          </button>
        </div>
      </div>

      {/* 后台 Daemon 资源透明监控指标网格 */}
      <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
          <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
            <Server className="w-3.5 h-3.5 text-indigo-400" />
            <span>进程 PID</span>
          </div>
          <div className="font-mono text-sm font-semibold text-slate-200">
            {daemonMetrics.isZombieCleaned ? '已终止' : daemonMetrics.pid}
          </div>
        </div>

        <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
          <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
            <Cpu className="w-3.5 h-3.5 text-sky-400" />
            <span>CPU 占用</span>
          </div>
          <div className="font-mono text-sm font-semibold text-slate-200">
            {daemonMetrics.cpuUsagePercent}%
          </div>
        </div>

        <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
          <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
            <Activity className="w-3.5 h-3.5 text-emerald-400" />
            <span>内存驻留</span>
          </div>
          <div className="font-mono text-sm font-semibold text-slate-200">
            {daemonMetrics.memoryUsageMb} MB
          </div>
        </div>

        <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
          <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
            <Radio className="w-3.5 h-3.5 text-amber-400" />
            <span>网络流量</span>
          </div>
          <div className="font-mono text-sm font-semibold text-slate-200">
            {daemonMetrics.networkTxKb} KB/s
          </div>
        </div>
      </div>

      {/* 底部保障与一键清理退出 */}
      <div className="mt-3 flex items-center justify-between pt-3 border-t border-slate-800/60 text-xs">
        <div className="flex items-center gap-1.5 text-slate-400 text-[11px]">
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
          <span>契约保障：退出即退出，不留僵尸常驻守护进程</span>
        </div>

        <button
          type="button"
          onClick={() => {
            killAndCleanZombieProcess();
          }}
          disabled={daemonMetrics.isZombieCleaned}
          className="flex items-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-2.5 py-1 text-xs font-medium text-rose-300 hover:bg-rose-500/20 disabled:opacity-50 transition-colors"
          aria-label="彻底清理退出后台进程"
        >
          <PowerOff className="w-3.5 h-3.5" />
          <span>{daemonMetrics.isZombieCleaned ? '已彻底清理' : 'Kill & Clean (彻底退出)'}</span>
        </button>
      </div>
    </section>
  );
};
