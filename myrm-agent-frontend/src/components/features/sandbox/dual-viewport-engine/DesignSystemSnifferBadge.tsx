import React from 'react';
import { Box, Code2, ShieldCheck, ToggleLeft, ToggleRight } from 'lucide-react';
import { useSandboxDualViewportStore } from './useSandboxDualViewportStore';

interface DesignSystemSnifferBadgeProps {
  className?: string;
}

export const DesignSystemSnifferBadge: React.FC<DesignSystemSnifferBadgeProps> = ({
  className = '',
}) => {
  const { designAssets, toggleAssetEnforcement } = useSandboxDualViewportStore();

  return (
    <section
      aria-label="前置设计系统与API契约嗅探看板"
      className={`flex items-center gap-2 overflow-x-auto py-1 px-3 bg-slate-900/60 border-b border-slate-800 text-xs ${className}`}
    >
      <div className="flex items-center gap-1.5 text-slate-400 font-medium shrink-0">
        <ShieldCheck className="w-3.5 h-3.5 text-indigo-400" />
        <span className="font-mono text-[11px]">Design System SSOT:</span>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        {designAssets.map((asset) => {
          return (
            <div
              key={asset.id}
              className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-mono border transition-colors ${
                asset.isEnforced
                  ? 'bg-indigo-500/10 border-indigo-500/30 text-indigo-300'
                  : 'bg-slate-800/40 border-slate-700/40 text-slate-500 line-through'
              }`}
              title={`${asset.description} (${asset.importPath})`}
            >
              {asset.category === 'component' ? (
                <Box className="w-3 h-3 text-indigo-400 shrink-0" />
              ) : (
                <Code2 className="w-3 h-3 text-sky-400 shrink-0" />
              )}
              <span className="font-semibold">{asset.name}</span>

              <button
                type="button"
                onClick={() => {
                  toggleAssetEnforcement(asset.id);
                }}
                className="ml-1 text-slate-400 hover:text-white"
                aria-label={`切换 ${asset.name} 强制约束`}
              >
                {asset.isEnforced ? (
                  <ToggleRight className="w-3.5 h-3.5 text-indigo-400" />
                ) : (
                  <ToggleLeft className="w-3.5 h-3.5 text-slate-500" />
                )}
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
};
