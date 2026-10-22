import React from 'react';
import { Briefcase, Code2, Sparkles } from 'lucide-react';
import { useWorkspaceThemingStore } from './useWorkspaceThemingStore';
import { WorkMode } from './workspaceThemingTypes';

interface DualWorkModeToggleSwitcherProps {
  className?: string;
  onModeChange?: (mode: WorkMode) => void;
}

export const DualWorkModeToggleSwitcher: React.FC<
  DualWorkModeToggleSwitcherProps
> = ({ className = '', onModeChange }) => {
  const currentMode = useWorkspaceThemingStore((state) => state.currentMode);
  const switchMode = useWorkspaceThemingStore((state) => state.switchMode);

  const handleModeSwitch = (mode: WorkMode) => {
    switchMode(mode);
    if (onModeChange) {
      onModeChange(mode);
    }
  };

  return (
    <div
      data-testid="dual-work-mode-switcher"
      className={`inline-flex items-center rounded-xl border border-border/60 bg-muted/30 p-1 shadow-2xs backdrop-blur-md select-none ${className}`}
    >
      {/* 编程模式 (Coding) 按钮 */}
      <button
        type="button"
        onClick={() => {
          handleModeSwitch('coding');
        }}
        aria-pressed={currentMode === 'coding'}
        aria-label="切换至编程极客模式"
        className={`relative flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
          currentMode === 'coding'
            ? 'bg-background text-foreground shadow-xs'
            : 'text-muted-foreground hover:text-foreground'
        }`}
      >
        <Code2 className="h-3.5 w-3.5" />
        <span>编程模式</span>
        {currentMode === 'coding' && (
          <span className="rounded bg-primary/15 px-1 text-[9px] font-mono text-primary">
            Dev
          </span>
        )}
      </button>

      {/* 通用工作模式 (Work) 按钮 */}
      <button
        type="button"
        onClick={() => {
          handleModeSwitch('work');
        }}
        aria-pressed={currentMode === 'work'}
        aria-label="切换至通用办公模式"
        className={`relative flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
          currentMode === 'work'
            ? 'bg-background text-foreground shadow-xs'
            : 'text-muted-foreground hover:text-foreground'
        }`}
      >
        <Briefcase className="h-3.5 w-3.5" />
        <span>通用办公</span>
        {currentMode === 'work' && (
          <span className="rounded bg-amber-500/15 px-1 text-[9px] font-mono text-amber-600 dark:text-amber-400">
            Work
          </span>
        )}
      </button>
    </div>
  );
};
