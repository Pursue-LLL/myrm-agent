/**
 * DualTrackModeSwitcher.tsx
 * 全局双轨视图胶囊切换器：业务极简模式 vs 深度工程模式秒切控制器
 */

import React from 'react';
import { Code2, Sparkles, Target, Wrench } from 'lucide-react';
import type { DualTrackViewMode } from './dualTrackTypes';
import { useDualTrackStore } from './useDualTrackStore';

export interface DualTrackModeSwitcherProps {
  className?: string;
  onModeChange?: (mode: DualTrackViewMode) => void;
}

export const DualTrackModeSwitcher: React.FC<DualTrackModeSwitcherProps> = ({
  className = '',
  onModeChange,
}) => {
  const viewMode = useDualTrackStore((state) => state.viewMode);
  const setViewMode = useDualTrackStore((state) => state.setViewMode);

  const handleSelectMode = (mode: DualTrackViewMode): void => {
    setViewMode(mode);
    if (onModeChange !== undefined) {
      onModeChange(mode);
    }
  };

  return (
    <nav
      data-testid="dual-track-mode-switcher"
      aria-label="视图模式切换器"
      className={`inline-flex items-center p-1 bg-slate-950/80 backdrop-blur-md rounded-full border border-slate-800 shadow-inner select-none ${className}`}
    >
      {/* 业务极简模式按钮 */}
      <button
        type="button"
        data-testid="switch-business-mode-btn"
        aria-pressed={viewMode === 'business'}
        onClick={() => handleSelectMode('business')}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
          viewMode === 'business'
            ? 'bg-blue-600 text-white shadow-md'
            : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
        }`}
        title="仅展示需求澄清、计划书、商业图表与直出工件，无技术噪音"
      >
        <Target className="w-3.5 h-3.5" />
        <span>业务极简模式</span>
        {viewMode === 'business' && (
          <Sparkles className="w-3 h-3 text-amber-300 animate-pulse" />
        )}
      </button>

      {/* 深度工程模式按钮 */}
      <button
        type="button"
        data-testid="switch-engineering-mode-btn"
        aria-pressed={viewMode === 'engineering'}
        onClick={() => handleSelectMode('engineering')}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
          viewMode === 'engineering'
            ? 'bg-slate-800 text-slate-100 border border-slate-700 shadow-md'
            : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
        }`}
        title="全量展开终端命令、代码 Diff、ToolCall 与物理断言测试记录"
      >
        <Wrench className="w-3.5 h-3.5 text-blue-400" />
        <span>深度工程模式</span>
        <Code2 className="w-3 h-3 text-slate-400" />
      </button>
    </nav>
  );
};
