import React from 'react';
import {
  PanelLeftClose,
  PanelLeftOpen,
  Layers,
  Sparkles,
  Workflow,
} from 'lucide-react';
import { useErgonomicCockpitStore } from './useErgonomicCockpitStore';
import { InlinePersonaAvatar } from './InlinePersonaAvatar';
import { InBubbleGaitHUD } from './InBubbleGaitHUD';
import type { ViewportMode } from './ergonomicCockpitTypes';

interface WideScreenErgonomicCockpitProps {
  children?: React.ReactNode;
  leftPanelSlot?: React.ReactNode;
  rightPanelSlot?: React.ReactNode;
  className?: string;
}

export const WideScreenErgonomicCockpit: React.FC<WideScreenErgonomicCockpitProps> = ({
  children,
  leftPanelSlot,
  rightPanelSlot,
  className = '',
}) => {
  const {
    viewportMode,
    isSidePanelsCollapsed,
    setViewportMode,
    toggleSidePanels,
  } = useErgonomicCockpitStore();

  const handleModeSwitch = (mode: ViewportMode): void => {
    setViewportMode(mode);
  };

  const getMaxWidthClass = (): string => {
    switch (viewportMode) {
      case 'compact':
        return 'max-w-3xl';
      case 'standard':
        return 'max-w-5xl';
      case 'wide_ergonomic':
        return 'max-w-7xl';
      case 'ultrawide':
        return 'max-w-[1920px]';
      default:
        return 'max-w-7xl';
    }
  };

  return (
    <section
      aria-label="宽屏人体工效学向心座舱"
      className={`relative flex h-full w-full flex-col bg-slate-950 text-slate-100 overflow-hidden ${className}`}
    >
      {/* 顶部人体工效学控制条 */}
      <header
        aria-label="人体工效学控制面板"
        className="flex h-11 shrink-0 items-center justify-between border-b border-slate-800/80 bg-slate-900/60 px-4 backdrop-blur-md"
      >
        <div className="flex items-center gap-3">
          <InlinePersonaAvatar />
          <div className="hidden sm:flex items-center gap-1.5 text-[11px] text-slate-400">
            <span className="w-1 h-1 rounded-full bg-indigo-500" />
            <span className="font-mono">Foveal Centric Layout</span>
          </div>
        </div>

        {/* 视界与侧栏联动控制按键组 */}
        <div className="flex items-center gap-2">
          {/* 模式切换器 */}
          <div className="flex items-center rounded-lg bg-slate-800/80 p-0.5 border border-slate-700/60 text-xs">
            <button
              type="button"
              onClick={() => {
                handleModeSwitch('compact');
              }}
              className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                viewportMode === 'compact'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              aria-label="切换至紧凑模式"
            >
              紧凑
            </button>
            <button
              type="button"
              onClick={() => {
                handleModeSwitch('standard');
              }}
              className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                viewportMode === 'standard'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              aria-label="切换至标准模式"
            >
              标准
            </button>
            <button
              type="button"
              onClick={() => {
                handleModeSwitch('wide_ergonomic');
              }}
              className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                viewportMode === 'wide_ergonomic'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              aria-label="切换至工效学宽屏模式"
            >
              工效学
            </button>
            <button
              type="button"
              onClick={() => {
                handleModeSwitch('ultrawide');
              }}
              className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                viewportMode === 'ultrawide'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              aria-label="切换至超宽屏模式"
            >
              带鱼屏
            </button>
          </div>

          {/* 侧栏向心折叠/展开按钮 */}
          <button
            type="button"
            onClick={() => {
              toggleSidePanels();
            }}
            className="flex items-center gap-1 rounded-lg border border-slate-700/60 bg-slate-800/80 px-2 py-1 text-xs text-slate-300 hover:bg-slate-700/80 transition-colors"
            aria-label={isSidePanelsCollapsed ? '展开双翼辅助面板' : '折叠双翼聚焦中轴'}
            title={isSidePanelsCollapsed ? '展开双翼辅助面板' : '折叠双翼聚焦中轴'}
          >
            {isSidePanelsCollapsed ? (
              <>
                <PanelLeftOpen className="w-3.5 h-3.5" />
                <span className="text-[11px]">展开辅助翼</span>
              </>
            ) : (
              <>
                <PanelLeftClose className="w-3.5 h-3.5" />
                <span className="text-[11px]">向心聚焦</span>
              </>
            )}
          </button>
        </div>
      </header>

      {/* 主体三栏布局容器 */}
      <div className="relative flex flex-1 w-full overflow-hidden justify-center">
        <div className={`flex h-full w-full ${getMaxWidthClass()} transition-all duration-300`}>
          {/* 左翼面板：智能体矩阵 / 拓扑导览 */}
          {!isSidePanelsCollapsed && (
            <aside
              aria-label="左侧智能体矩阵面板"
              className="hidden lg:flex w-64 shrink-0 flex-col border-r border-slate-800/80 bg-slate-900/40 p-3 overflow-y-auto"
            >
              <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                <Workflow className="w-3.5 h-3.5 text-indigo-400" />
                <span>智能体协同拓扑</span>
              </div>
              {leftPanelSlot ? (
                leftPanelSlot
              ) : (
                <div className="flex flex-col gap-2 text-xs text-slate-400">
                  <div className="p-2.5 rounded-lg border border-slate-800 bg-slate-900/60">
                    <div className="font-medium text-slate-200">主干会话协调员</div>
                    <div className="text-[11px] text-slate-500 mt-0.5">掌舵中轴会话流交互</div>
                  </div>
                  <div className="p-2.5 rounded-lg border border-slate-800/60 bg-slate-900/30">
                    <div className="font-medium text-slate-300">后台研判沙箱</div>
                    <div className="text-[11px] text-slate-500 mt-0.5">无阻塞实时推演测试</div>
                  </div>
                </div>
              )}
            </aside>
          )}

          {/* 中轴核心会话区：向心聚焦黄金视界 */}
          <main
            role="main"
            aria-label="中轴对话核心视界"
            className="flex flex-1 flex-col h-full min-w-0 bg-slate-950 relative overflow-hidden"
          >
            {/* 顶置解耦步态视窗 */}
            <div className="px-4 pt-3 pb-1 shrink-0">
              <InBubbleGaitHUD />
            </div>

            {/* 会话流主视窗内容槽位 */}
            <div className="flex-1 overflow-y-auto px-4 py-2">
              {children ? (
                children
              ) : (
                <section
                  aria-label="会话流占位"
                  className="flex h-full flex-col items-center justify-center text-slate-500 gap-2"
                >
                  <Sparkles className="w-8 h-8 text-indigo-500/40" />
                  <p className="text-sm">宽屏大视界人体工效学向心对话就绪</p>
                  <span className="text-xs text-slate-600 font-mono">
                    Mode: {viewportMode} · Centered Foveal Alignment
                  </span>
                </section>
              )}
            </div>
          </main>

          {/* 右翼面板：工件/产物/巡检实时联动看板 */}
          {!isSidePanelsCollapsed && (
            <aside
              aria-label="右侧工件实时联动画板"
              className="hidden xl:flex w-80 shrink-0 flex-col border-l border-slate-800/80 bg-slate-900/40 p-3 overflow-y-auto"
            >
              <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                <Layers className="w-3.5 h-3.5 text-sky-400" />
                <span>实时任务产物看板</span>
              </div>
              {rightPanelSlot ? (
                rightPanelSlot
              ) : (
                <div className="flex flex-col gap-2 text-xs text-slate-400">
                  <div className="p-3 rounded-lg border border-slate-800 bg-slate-900/60">
                    <div className="font-medium text-slate-200">实时工件流水线</div>
                    <div className="text-[11px] text-slate-500 mt-1">
                      大屏下左右双翼与中轴保持黄金视距，无需扭头疲劳寻觅
                    </div>
                  </div>
                </div>
              )}
            </aside>
          )}
        </div>
      </div>
    </section>
  );
};
