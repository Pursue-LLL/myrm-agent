'use client';

import React from 'react';
import {
  X,
  Sparkles,
  Check,
  Palette,
  Layout,
  ArrowRight,
  Eye,
} from 'lucide-react';
import { useDesignIntentStore } from './useDesignIntentStore';
import { DesignDirectionVariant } from './designIntentTypes';

export const MultiDirectionDivergenceDeck: React.FC = () => {
  const {
    variants,
    selectedVariantId,
    isExplorationOpen,
    selectVariant,
    closeExploration,
  } = useDesignIntentStore();

  if (!isExplorationOpen) {
    return null;
  }

  const selectedVariant =
    variants.find((v) => v.id === selectedVariantId) || variants[0];

  const renderVariantCard = (variant: DesignDirectionVariant) => {
    const isSelected = selectedVariantId === variant.id;

    return (
      <div
        key={variant.id}
        onClick={() => { selectVariant(variant.id); }}
        role="presentation"
        className={`relative flex flex-col justify-between rounded-2xl border p-4 transition-all duration-200 cursor-pointer select-none ${
          isSelected
            ? 'bg-slate-900/95 border-sky-500 shadow-2xl shadow-sky-950/50 ring-2 ring-sky-500/50'
            : 'bg-slate-900/60 border-slate-800 hover:border-slate-700 hover:bg-slate-900/80'
        }`}
      >
        {/* 顶部标签与选中徽章 */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span
              className="text-[11px] font-semibold px-2 py-0.5 rounded-full border"
              style={{
                color: variant.primaryColor,
                borderColor: `${variant.primaryColor}40`,
                backgroundColor: `${variant.primaryColor}15`,
              }}
            >
              {variant.aestheticCategory}
            </span>

            <div
              className={`w-5 h-5 rounded-full flex items-center justify-center transition-colors ${
                isSelected
                  ? 'bg-sky-500 text-white'
                  : 'border border-slate-700 bg-slate-800 text-transparent'
              }`}
            >
              <Check className="w-3.5 h-3.5 stroke-[2.5]" aria-hidden="true" />
            </div>
          </div>

          <h4 className="text-sm font-bold text-slate-100 mb-1">
            {variant.title}
          </h4>
          <p className="text-xs text-slate-400 mb-3 line-clamp-2">
            {variant.subtitle}
          </p>

          {/* 调色指示条 */}
          <div className="flex items-center space-x-1.5 mb-3.5">
            <Palette className="w-3 h-3 text-slate-500" aria-hidden="true" />
            <div
              className="w-4 h-4 rounded-full border border-white/20"
              style={{ backgroundColor: variant.primaryColor }}
              title={`主色: ${variant.primaryColor}`}
            />
            <div
              className="w-4 h-4 rounded-full border border-white/20"
              style={{ backgroundColor: variant.accentColor }}
              title={`强调色: ${variant.accentColor}`}
            />
            <span className="text-[10px] text-slate-500 font-mono ml-1">
              {variant.primaryColor}
            </span>
          </div>

          {/* 初稿骨架预览展板 (Prototype Skeleton Preview) */}
          <div
            className="w-full h-36 rounded-xl border border-slate-800 p-3 flex flex-col justify-between overflow-hidden shadow-inner mb-3"
            style={{ backgroundColor: variant.backgroundColor }}
          >
            {variant.previewLayers.map((layer) => {
              if (layer.type === 'text') {
                return (
                  <div
                    key={layer.id}
                    className="text-xs font-bold truncate select-none"
                    style={{ color: layer.color || '#ffffff' }}
                  >
                    {layer.text}
                  </div>
                );
              }
              if (layer.type === 'button') {
                return (
                  <div
                    key={layer.id}
                    className="flex items-center justify-center text-[10px] font-semibold py-1.5 px-3 select-none"
                    style={{
                      backgroundColor: layer.bg,
                      color: layer.color || '#ffffff',
                      borderRadius: `${layer.borderRadius || 6}px`,
                    }}
                  >
                    {layer.text}
                  </div>
                );
              }
              return (
                <div
                  key={layer.id}
                  style={{
                    backgroundColor: layer.bg,
                    height: `${layer.height || 8}px`,
                    borderRadius: `${layer.borderRadius || 4}px`,
                  }}
                  className="w-full"
                />
              );
            })}
          </div>

          <p className="text-[11px] text-slate-400 leading-relaxed">
            {variant.summary}
          </p>
        </div>

        {/* 底部选择操作 */}
        <div className="mt-4 pt-3 border-t border-slate-800 flex items-center justify-between">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              selectVariant(variant.id);
            }}
            className={`w-full py-1.5 px-3 rounded-lg text-xs font-semibold flex items-center justify-center space-x-1.5 transition-all ${
              isSelected
                ? 'bg-sky-500 text-white shadow-md shadow-sky-950/40'
                : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            {isSelected ? (
              <>
                <Check className="w-3.5 h-3.5" aria-hidden="true" />
                <span>已选定此方向深化</span>
              </>
            ) : (
              <>
                <Eye className="w-3.5 h-3.5" aria-hidden="true" />
                <span>选择此方向</span>
              </>
            )}
          </button>
        </div>
      </div>
    );
  };

  return (
    <dialog
      open
      aria-label="多方向初稿探索选型中枢"
      className="fixed inset-0 z-50 flex flex-col w-full h-full max-w-none max-h-none m-0 p-0 border-0 bg-slate-950/90 backdrop-blur-xl animate-in fade-in duration-200"
    >
      {/* 顶部标题栏 */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/60">
        <div className="flex items-center space-x-2.5">
          <div className="p-2 bg-indigo-500/10 border border-indigo-500/30 rounded-xl">
            <Layout className="w-5 h-5 text-indigo-400" aria-hidden="true" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="text-base font-bold text-slate-100">
                多方向初稿铺开与决策选型
              </h3>
              <span className="text-[11px] bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 px-2 py-0.5 rounded-full font-medium">
                先立骨架 · 把可能性铺开
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              AI 围绕意图五要素生成 3 组截然不同的美学表达，您只需专注审美判断与方向裁决
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={closeExploration}
          className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg transition-colors"
          title="关闭选型中枢"
        >
          <X className="w-5 h-5" aria-hidden="true" />
        </button>
      </header>

      {/* 3 方向并排平铺预览区域 */}
      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-6xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-5">
          {variants.map((v) => renderVariantCard(v))}
        </div>
      </main>

      {/* 底部确认行动栏 */}
      <footer className="flex items-center justify-between px-6 py-3.5 border-t border-slate-800 bg-slate-900/80 backdrop-blur-md">
        <div className="flex items-center space-x-2 text-xs">
          <span className="text-slate-400">当前锁定决策:</span>
          <span className="font-semibold text-sky-400 bg-sky-950/60 border border-sky-800/60 px-2.5 py-1 rounded-md">
            {selectedVariant.title} · {selectedVariant.aestheticCategory}
          </span>
        </div>

        <div className="flex items-center space-x-3">
          <button
            type="button"
            onClick={closeExploration}
            className="px-3.5 py-2 text-xs text-slate-400 hover:text-slate-200 transition-colors"
          >
            稍后决定
          </button>

          <button
            type="button"
            onClick={closeExploration}
            className="flex items-center space-x-1.5 px-4 py-2 bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white rounded-xl text-xs font-semibold shadow-lg shadow-sky-950/50 transition-all hover:scale-[1.02] active:scale-[0.98]"
          >
            <Sparkles className="w-4 h-4" aria-hidden="true" />
            <span>确认锁定并载入画布深化</span>
            <ArrowRight className="w-3.5 h-3.5 ml-1" aria-hidden="true" />
          </button>
        </div>
      </footer>
    </dialog>
  );
};
