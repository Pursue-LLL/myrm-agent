import React from 'react';
import { Sparkles, ArrowRight, X, Database } from 'lucide-react';
import { useDataMigrationStore } from './useDataMigrationStore';
import { formatSourceTypeLabel } from './dataMigrationEngine';

export interface MigrationSilentToastProps {
  className?: string;
}

export const MigrationSilentToast: React.FC<MigrationSilentToastProps> = ({
  className = '',
}) => {
  const {
    showSilentToast,
    activeReport,
    dismissSilentToast,
    toggleReconciliationModal,
  } = useDataMigrationStore();

  if (!showSilentToast || !activeReport) {
    return null;
  }

  const totalAssetsCount =
    activeReport.tasks.total +
    activeReport.cronJobs.total +
    activeReport.memories.total +
    activeReport.mcpConfigs.total;

  const handleOpenModal = () => {
    dismissSilentToast();
    toggleReconciliationModal(true);
  };

  return (
    <div
      data-testid="migration-silent-toast"
      aria-live="polite"
      className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 p-3.5 pr-2.5 rounded-2xl bg-zinc-900/98 backdrop-blur-xl border border-indigo-500/30 shadow-[0_8px_30px_rgba(0,0,0,0.6)] animate-fade-in font-sans ${className}`}
    >
      <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shrink-0">
        <Sparkles className="w-4 h-4 animate-pulse" />
      </div>

      <div className="space-y-0.5 pr-2">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-bold text-zinc-100">
            已静默探测到历史智能体资产
          </span>
          <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
            {totalAssetsCount} 项
          </span>
        </div>
        <p className="text-[11px] text-zinc-400 font-mono">
          来源: {formatSourceTypeLabel(activeReport.sourceType)}
        </p>
      </div>

      <div className="flex items-center gap-1 shrink-0">
        <button
          type="button"
          onClick={handleOpenModal}
          className="flex items-center gap-1 px-3 py-1.5 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl shadow transition-colors"
        >
          <span>查看对账单</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </button>

        <button
          type="button"
          onClick={dismissSilentToast}
          aria-label="关闭提示"
          title="关闭"
          className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};
