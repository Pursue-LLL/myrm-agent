import React, { useState } from 'react';
import {
  Stethoscope,
  ShieldCheck,
  Database,
  Share2,
  Wrench,
  Brain,
  CheckCircle2,
  Loader2,
  Copy,
  Check,
} from 'lucide-react';
import { useCommandCenterStore } from './useCommandCenterStore';
import { MaintenanceActionType } from './commandCenterTypes';

interface ActionCardConfig {
  action: MaintenanceActionType;
  title: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  toneColor: string;
}

export const CommandCenterMaintenanceTab: React.FC = () => {
  const {
    maintenanceTask,
    runMaintenanceAction,
    generateDebugShare,
    debugSharePayload,
  } = useCommandCenterStore();

  const [copiedDebug, setCopiedDebug] = useState(false);

  const actionCards: ActionCardConfig[] = [
    {
      action: 'doctor',
      title: '一键运行 Doctor 诊断',
      description: '全面检测 Python Server 进程、本地网关端口占用与依赖完整性',
      icon: Stethoscope,
      toneColor: 'text-emerald-400 border-emerald-500/30 hover:border-emerald-500/60',
    },
    {
      action: 'security_audit',
      title: '系统安全合规审计',
      description: '排查沙箱命令权限、只读文件边界与凭据防泄漏合规状态',
      icon: ShieldCheck,
      toneColor: 'text-indigo-400 border-indigo-500/30 hover:border-indigo-500/60',
    },
    {
      action: 'backup_sqlite',
      title: '创建 SQLite/Volume 备份',
      description: '即时快照持久化会话库、Agent 记忆与物理项目工作区元数据',
      icon: Database,
      toneColor: 'text-sky-400 border-sky-500/30 hover:border-sky-500/60',
    },
    {
      action: 'debug_share',
      title: '生成 Debug Share 排障包',
      description: '一键打包近 100 行已脱敏日志与系统自检报告供排障定位',
      icon: Share2,
      toneColor: 'text-amber-400 border-amber-500/30 hover:border-amber-500/60',
    },
    {
      action: 'skill_curator',
      title: 'Skill Curator 依赖体检',
      description: '自动扫描本地注册技能健康度，智能修剪失效与无用插件',
      icon: Wrench,
      toneColor: 'text-purple-400 border-purple-500/30 hover:border-purple-500/60',
    },
    {
      action: 'memory_reset',
      title: '记忆切片整理与压缩',
      description: '清理过期的临时对话向量索引，压缩高频记忆碎片提升检索速度',
      icon: Brain,
      toneColor: 'text-rose-400 border-rose-500/30 hover:border-rose-500/60',
    },
  ];

  const handleRunAction = (action: MaintenanceActionType) => {
    if (action === 'debug_share') {
      generateDebugShare();
    }
    runMaintenanceAction(action);
  };

  const handleCopyDebugShare = () => {
    if (debugSharePayload) {
      navigator.clipboard?.writeText(debugSharePayload);
      setCopiedDebug(true);
      setTimeout(() => {
        setCopiedDebug(false);
      }, 2000);
    }
  };

  return (
    <div
      data-testid="command-center-maintenance-tab"
      className="flex flex-col h-[460px] select-none text-slate-200 overflow-y-auto pr-1"
    >
      {/* 维护动作卡片网格 */}
      <div className="grid grid-cols-2 gap-3 mb-3">
        {actionCards.map((card) => {
          const IconComponent = card.icon;
          const isCurrentRunning =
            maintenanceTask.status === 'running' &&
            maintenanceTask.action === card.action;

          return (
            <div
              key={card.action}
              className={`p-3.5 rounded-xl bg-slate-900/60 border transition-all flex flex-col justify-between ${card.toneColor}`}
            >
              <div>
                <div className="flex items-center gap-2 mb-1.5">
                  <IconComponent className="w-4 h-4 shrink-0" />
                  <span className="font-semibold text-xs text-slate-100">
                    {card.title}
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  {card.description}
                </p>
              </div>

              <div className="mt-3 pt-2 border-t border-slate-800/80 flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => handleRunAction(card.action)}
                  disabled={maintenanceTask.status === 'running'}
                  className="px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 transition-colors disabled:opacity-50"
                >
                  {isCurrentRunning ? (
                    <span className="inline-flex items-center gap-1">
                      <Loader2 className="w-3 h-3 animate-spin" />
                      <span>执行中</span>
                    </span>
                  ) : (
                    <span>立即执行</span>
                  )}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* 任务执行状态反馈条 */}
      {maintenanceTask.status !== 'idle' && (
        <div
          data-testid="maintenance-task-status"
          className="p-3 bg-slate-900/90 border border-slate-800 rounded-xl mb-3 flex items-center justify-between text-xs animate-in fade-in duration-150"
        >
          <div className="flex items-center gap-2">
            {maintenanceTask.status === 'running' ? (
              <Loader2 className="w-4 h-4 text-indigo-400 animate-spin" />
            ) : (
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            )}
            <span className="text-slate-200">{maintenanceTask.message}</span>
          </div>
          <span className="text-xs font-mono font-bold text-indigo-400">
            {maintenanceTask.progressPercent}%
          </span>
        </div>
      )}

      {/* Debug Share 排障包预览浮层 */}
      {debugSharePayload && (
        <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl text-xs flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-slate-300">
              Debug Share 脱敏排障包已生成
            </span>
            <button
              type="button"
              onClick={handleCopyDebugShare}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs transition-colors"
            >
              {copiedDebug ? (
                <>
                  <Check className="w-3 h-3 text-emerald-400" />
                  <span>已复制</span>
                </>
              ) : (
                <>
                  <Copy className="w-3 h-3" />
                  <span>复制脱敏包</span>
                </>
              )}
            </button>
          </div>
          <pre className="max-h-24 overflow-y-auto text-[10px] font-mono text-slate-400 p-2 bg-slate-900/70 rounded border border-slate-800/80">
            {debugSharePayload.substring(0, 300)}...
          </pre>
        </div>
      )}
    </div>
  );
};
