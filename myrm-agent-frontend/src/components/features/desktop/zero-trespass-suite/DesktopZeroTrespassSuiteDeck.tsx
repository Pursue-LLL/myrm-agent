import React from 'react';
import {
  DownloadCloud,
  FileCheck2,
  HardDriveDownload,
  Laptop,
  Layers,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { useZeroTrespassStore } from './useZeroTrespassStore';
import { AutostartTransparentDaemonHUD } from './AutostartTransparentDaemonHUD';
import { TokenCostBudgetGateHUD } from './TokenCostBudgetGateHUD';
import { StepSaverQuantificationCard } from './StepSaverQuantificationCard';

interface DesktopZeroTrespassSuiteDeckProps {
  className?: string;
}

export const DesktopZeroTrespassSuiteDeck: React.FC<DesktopZeroTrespassSuiteDeckProps> = ({
  className = '',
}) => {
  const { deltaOta, updateDeltaOtaStatus } = useZeroTrespassStore();

  return (
    <section
      aria-label="桌面端零越界用户授权与全链路透明沙盒套件主看板"
      className={`relative flex h-full w-full flex-col bg-slate-950 text-slate-100 overflow-y-auto p-4 sm:p-6 space-y-4 ${className}`}
    >
      {/* 顶栏标题与微差量 OTA 徽章 */}
      <header
        aria-label="零越界套件顶栏"
        className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-800"
      >
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <Laptop className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-white tracking-tight">
                桌面端零越界授权与透明信任中枢
              </h2>
              <span className="rounded bg-emerald-500/10 px-2 py-0.5 text-[10px] font-mono text-emerald-400 border border-emerald-500/20">
                Zero-Trespass Verified
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              消除流氓自启与偷偷扣费 · 物理模型防降级 · 变废为宝
            </p>
          </div>
        </div>

        {/* 微差量 OTA 静默热更指示器 */}
        <div className="flex items-center gap-3 rounded-xl bg-slate-900/90 border border-slate-800 p-2.5 text-xs">
          <div className="p-1.5 rounded-lg bg-sky-500/10 text-sky-400 border border-sky-500/20">
            <DownloadCloud className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-slate-200">Zstd 微差量热更 ({deltaOta.versionTag})</span>
              <span className="rounded bg-indigo-500/20 px-1.5 py-0.2 text-[10px] font-mono text-indigo-300">
                省流量 {deltaOta.bandwidthSavedPercent}%
              </span>
            </div>
            <div className="text-[11px] text-slate-400 font-mono mt-0.5">
              本次仅拉取 <span className="text-sky-400 font-bold">{deltaOta.patchSizeKb} KB</span>（免下载 {deltaOta.fullPackageSizeMb} MB 全量包）
            </div>
          </div>
        </div>
      </header>

      {/* 模块一：零越界自启动契约与后台常驻透明看板 */}
      <AutostartTransparentDaemonHUD />

      {/* 模块二：全链路 Token 成本预算与真实模型防降级遥测 */}
      <TokenCostBudgetGateHUD />

      {/* 模块三：“帮你省了哪一步”价值量化与诚实能力边界 */}
      <StepSaverQuantificationCard />
    </section>
  );
};
