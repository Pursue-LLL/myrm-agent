import React from 'react';
import { Sparkles, ArrowRight, X, Radio, Layers } from 'lucide-react';
import { useMigrationWizardStore } from './useMigrationWizardStore';

export const MigrationScanBanner: React.FC = () => {
  const { isBannerVisible, radarReport, openDrawer, dismissBanner } =
    useMigrationWizardStore();

  if (!isBannerVisible || !radarReport.hasDetectedAssets) {
    return null;
  }

  const { agents, skills, mcpServers, totalAssetsCount } = radarReport;

  return (
    <aside
      aria-label="本地多生态智能体配置无感雷达扫描横幅"
      className="p-3.5 border rounded-xl bg-gradient-to-r from-sky-950/60 via-indigo-950/40 to-slate-900 border-sky-500/30 text-slate-100 shadow-md animate-in fade-in slide-in-from-top-2 duration-150"
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-start sm:items-center gap-3">
          <div className="p-2 rounded-lg bg-sky-500/10 text-sky-400 border border-sky-500/20 shrink-0">
            <Radio className="w-4 h-4 animate-pulse" />
          </div>
          <div className="space-y-0.5">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-white">
                雷达已自动探针到本地竞品资产
              </span>
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-mono rounded bg-sky-900/60 text-sky-300 border border-sky-700/50">
                <Sparkles className="w-2.5 h-2.5 text-amber-400" />
                共 {totalAssetsCount} 项
              </span>
            </div>
            <p className="text-xs text-slate-300">
              包含 OpenClaw / Hermes / Cursor 中保存的{' '}
              <span className="font-semibold text-sky-300">{agents.length} 个智能体</span>、
              <span className="font-semibold text-sky-300">{skills.length} 个自研技能</span>与{' '}
              <span className="font-semibold text-sky-300">{mcpServers.length} 个 MCP 服务</span>
              。无需手动敲 SSH，支持一键无损迁移至 Myrm。
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
          <button
            type="button"
            onClick={openDrawer}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors border rounded-lg bg-sky-600 hover:bg-sky-500 text-white border-sky-500 shadow-sm"
          >
            <span>一键免 SSH 搬家</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={dismissBanner}
            className="p-1.5 transition-colors rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
            aria-label="关闭横幅"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>
  );
};
