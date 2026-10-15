import React from 'react';
import {
  X,
  FileSpreadsheet,
  CheckCircle2,
  AlertTriangle,
  Layers,
  Clock,
  Brain,
  Cpu,
  ArrowRight,
  ShieldCheck,
} from 'lucide-react';
import { useDataMigrationStore } from './useDataMigrationStore';
import { ConflictStrategy } from './dataMigrationTypes';
import { formatSourceTypeLabel } from './dataMigrationEngine';

export interface MigrationReconciliationModalProps {
  className?: string;
}

export const MigrationReconciliationModal: React.FC<MigrationReconciliationModalProps> = ({
  className = '',
}) => {
  const {
    isReconciliationModalOpen,
    activeReport,
    conflictStrategy,
    status,
    toggleReconciliationModal,
    setConflictStrategy,
    executeImport,
  } = useDataMigrationStore();

  if (!isReconciliationModalOpen || !activeReport) {
    return null;
  }

  const handleClose = () => {
    toggleReconciliationModal(false);
  };

  const handleConfirmImport = () => {
    executeImport();
  };

  const categories = [
    {
      title: '历史任务记录 (Tasks)',
      stats: activeReport.tasks,
      icon: Layers,
      color: 'text-indigo-400',
    },
    {
      title: '周期性作业 (Cron Jobs)',
      stats: activeReport.cronJobs,
      icon: Clock,
      color: 'text-amber-400',
    },
    {
      title: '长短期记忆 (Memories)',
      stats: activeReport.memories,
      icon: Brain,
      color: 'text-cyan-400',
    },
    {
      title: 'MCP 外部服务 (Tools)',
      stats: activeReport.mcpConfigs,
      icon: Cpu,
      color: 'text-emerald-400',
    },
  ];

  const totalNew =
    activeReport.tasks.newCount +
    activeReport.cronJobs.newCount +
    activeReport.memories.newCount +
    activeReport.mcpConfigs.newCount;

  const totalDuplicates =
    activeReport.tasks.duplicateCount +
    activeReport.cronJobs.duplicateCount +
    activeReport.memories.duplicateCount +
    activeReport.mcpConfigs.duplicateCount;

  return (
    <div
      data-testid="migration-reconciliation-modal"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in font-sans"
    >
      <div
        className={`relative w-full max-w-xl rounded-2xl border border-zinc-800 bg-zinc-900 shadow-2xl p-6 space-y-4 max-h-[90vh] flex flex-col ${className}`}
      >
        {/* 1. 模态头部 */}
        <header className="flex items-center justify-between pb-3 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <FileSpreadsheet className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-zinc-100">历史资产迁移对账单</h3>
              <p className="text-[11px] text-zinc-400 font-mono">
                来源: {formatSourceTypeLabel(activeReport.sourceType)}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleClose}
            aria-label="关闭对账单"
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        {/* 2. 对账统计胶囊 */}
        <div className="flex items-center justify-between p-2.5 rounded-xl bg-zinc-950 border border-zinc-850 text-xs font-mono">
          <span className="text-zinc-300 flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            待新增资产: <strong className="text-emerald-300">{totalNew} 项</strong>
          </span>
          <span className="text-zinc-400 flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
            检测到重复项: <strong className="text-amber-300">{totalDuplicates} 项</strong>
          </span>
        </div>

        {/* 3. 四维资产明细列表 */}
        <div className="flex-1 overflow-y-auto space-y-2 pr-1">
          {categories.map((cat, idx) => {
            const Icon = cat.icon;
            return (
              <div
                key={`cat-${idx}`}
                className="p-3 rounded-xl bg-zinc-950/60 border border-zinc-850 text-xs space-y-1.5"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-zinc-200 flex items-center gap-1.5">
                    <Icon className={`w-3.5 h-3.5 ${cat.color}`} />
                    {cat.title}
                  </span>
                  <span className="text-[11px] font-mono text-zinc-400">
                    共 {cat.stats.total} 项
                  </span>
                </div>

                <div className="flex items-center gap-3 text-[11px] font-mono text-zinc-400 pt-0.5 border-t border-zinc-850/60">
                  <span className="text-emerald-400">
                    + {cat.stats.newCount} 新增
                  </span>
                  {cat.stats.duplicateCount > 0 ? (
                    <span className="text-amber-400">
                      ⚠ {cat.stats.duplicateCount} 重复
                    </span>
                  ) : (
                    <span className="text-zinc-500">无重复</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* 4. 冲突解决策略选择 */}
        <div className="p-3 rounded-xl bg-zinc-950/80 border border-zinc-800 space-y-2 text-xs">
          <span className="font-semibold text-zinc-300 flex items-center gap-1">
            <ShieldCheck className="w-3.5 h-3.5 text-indigo-400" />
            重复项合并策略:
          </span>

          <div className="grid grid-cols-3 gap-2">
            {[
              { key: 'skip', label: '跳过重复项', desc: '保留本地数据' },
              { key: 'overwrite', label: '覆盖现有项', desc: '以历史旧版为准' },
              { key: 'rename', label: '自动重命名', desc: '新旧两份均保留' },
            ].map((strat) => {
              const isSelected = conflictStrategy === strat.key;
              return (
                <button
                  key={strat.key}
                  type="button"
                  onClick={() => {
                    setConflictStrategy(strat.key as ConflictStrategy);
                  }}
                  className={`p-2 rounded-lg text-left border transition-all ${
                    isSelected
                      ? 'bg-indigo-600/20 border-indigo-500 text-indigo-200'
                      : 'bg-zinc-900 border-zinc-800 text-zinc-400 hover:border-zinc-700'
                  }`}
                >
                  <div className="font-semibold text-[11px]">{strat.label}</div>
                  <div className="text-[10px] text-zinc-500 mt-0.5">{strat.desc}</div>
                </button>
              );
            })}
          </div>
        </div>

        {/* 5. 底部操作按钮 */}
        <footer className="pt-2 flex items-center justify-end gap-2 border-t border-zinc-800">
          <button
            type="button"
            onClick={handleClose}
            className="px-4 py-2 text-xs text-zinc-400 hover:text-zinc-200 rounded-xl"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleConfirmImport}
            disabled={status === 'importing'}
            className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl shadow transition-colors disabled:opacity-40"
          >
            <span>确认无损迁移导入</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </footer>
      </div>
    </div>
  );
};
