import React from 'react';
import {
  Zap,
  X,
  ArrowRight,
  Cpu,
  Coins,
  ShieldCheck,
  Check,
  AlertCircle,
} from 'lucide-react';
import { useModelSpotlightStore } from './useModelSpotlightStore';
import {
  computeMountComparison,
  formatTokenCount,
} from './spotlightCatalogData';

export const SpotlightMountConfirmModal: React.FC = () => {
  const {
    isMountModalOpen,
    mountTargetSpotlight,
    currentAgentModelId,
    closeMountModal,
    confirmMountModel,
  } = useModelSpotlightStore();

  if (!isMountModalOpen || !mountTargetSpotlight) {
    return null;
  }

  const comparison = computeMountComparison(
    currentAgentModelId,
    mountTargetSpotlight
  );

  const handleConfirm = () => {
    confirmMountModel(mountTargetSpotlight);
  };

  return (
    <>
      <div
        className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm transition-opacity"
        aria-hidden="true"
      />
      <dialog
        open
        aria-labelledby="mount-modal-title"
        className="fixed inset-0 z-50 m-auto w-full max-w-lg bg-slate-900 border border-slate-700/80 rounded-xl shadow-2xl p-0 flex flex-col text-slate-100 overflow-hidden"
        data-testid="spotlight-mount-modal"
      >
        {/* 弹窗头部 */}
        <header className="px-5 py-4 border-b border-slate-800 bg-slate-950/60 flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="p-2 rounded-lg bg-amber-500/20 text-amber-400 border border-amber-500/30">
              <Zap className="w-4 h-4 fill-current" />
            </div>
            <div>
              <h3 id="mount-modal-title" className="font-bold text-sm text-white">
                一键热挂载前沿模型
              </h3>
              <p className="text-xs text-slate-400">
                将当前智能体主推理引擎无损切换至最新发布模型
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={closeMountModal}
            aria-label="关闭挂载窗口"
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        {/* 模型迁移路径对比 */}
        <div className="p-5 space-y-4 text-xs">
          <div className="bg-slate-950/50 p-3.5 rounded-lg border border-slate-800 flex items-center justify-between">
            <div className="flex-1 min-w-0 pr-2">
              <div className="text-[11px] text-slate-400 mb-0.5">当前使用模型</div>
              <div className="font-medium text-slate-200 truncate">
                {comparison.currentModelId}
              </div>
              <div className="text-[10px] text-slate-500 font-mono mt-0.5">
                {formatTokenCount(comparison.currentContextWindow)} 上下文
              </div>
            </div>

            <div className="px-2 text-indigo-400">
              <ArrowRight className="w-4 h-4" />
            </div>

            <div className="flex-1 min-w-0 pl-2">
              <div className="text-[11px] text-indigo-300 font-semibold mb-0.5">
                升级目标模型
              </div>
              <div className="font-bold text-white truncate">
                {mountTargetSpotlight.name}
              </div>
              <div className="text-[10px] text-indigo-400 font-mono mt-0.5">
                {formatTokenCount(comparison.targetContextWindow)} 上下文
              </div>
            </div>
          </div>

          {/* 核心指标变更看板 */}
          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 rounded-lg bg-slate-800/60 border border-slate-700/60">
              <div className="flex items-center text-slate-400 mb-1 space-x-1">
                <Cpu className="w-3.5 h-3.5 text-sky-400" />
                <span>上下文容量变动</span>
              </div>
              <div className="text-sm font-bold text-white">
                {formatTokenCount(comparison.targetContextWindow)}
              </div>
              <div className="text-[10px] text-emerald-400 font-medium mt-0.5">
                {comparison.contextDeltaTokens >= 0 ? '+' : ''}
                {formatTokenCount(comparison.contextDeltaTokens)} Tokens
              </div>
            </div>

            <div className="p-3 rounded-lg bg-slate-800/60 border border-slate-700/60">
              <div className="flex items-center text-slate-400 mb-1 space-x-1">
                <Coins className="w-3.5 h-3.5 text-amber-400" />
                <span>费率基准预算</span>
              </div>
              <div className="text-sm font-bold text-white">
                ${mountTargetSpotlight.pricingInputPerM} / 1M
              </div>
              <div
                className={`text-[10px] font-medium mt-0.5 ${
                  comparison.priceDeltaPercent <= 0
                    ? 'text-emerald-400'
                    : 'text-amber-400'
                }`}
              >
                {comparison.priceDeltaPercent > 0 ? '+' : ''}
                {comparison.priceDeltaPercent}% 相对当前
              </div>
            </div>
          </div>

          {/* 继承与无损保障提示 */}
          <div className="p-3 rounded-lg bg-indigo-950/30 border border-indigo-800/50 space-y-1.5">
            <div className="font-semibold text-indigo-300 flex items-center space-x-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-indigo-400" />
              <span>无损热挂载保障机制</span>
            </div>
            <ul className="text-slate-300 text-[11px] space-y-1 pl-4 list-disc">
              <li>保留智能体既有 System Prompt、记忆库与已绑定的 MCP 工具链</li>
              <li>自动继承温度 (temperature) 与生成参数配置</li>
              <li>若新模型支持视觉/深度推理，自动激活相关模式支持</li>
            </ul>
          </div>

          {mountTargetSpotlight.discountPercent && (
            <div className="flex items-center space-x-1.5 text-amber-300 bg-amber-500/10 p-2 rounded border border-amber-500/30">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              <span>
                限时活动：当前享受 {mountTargetSpotlight.discountPercent}% 官方结算优惠
              </span>
            </div>
          )}
        </div>

        {/* 底部操作区 */}
        <footer className="px-5 py-3 border-t border-slate-800 bg-slate-950/60 flex items-center justify-end space-x-2">
          <button
            type="button"
            onClick={closeMountModal}
            className="px-3.5 py-1.5 text-xs text-slate-300 hover:text-white hover:bg-slate-800 rounded font-medium transition-colors"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            aria-label="确认热挂载此模型"
            className="px-4 py-1.5 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded shadow flex items-center space-x-1.5 transition-all"
          >
            <Check className="w-3.5 h-3.5" />
            <span>确认热挂载并生效</span>
          </button>
        </footer>
      </dialog>
    </>
  );
};
