/**
 * In-Situ Workflow Skill Picker Drawer
 * 会话上下文内就地工作流技能探索抽屉、Sash 拖拽手柄与动作空间噪声看板
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. a11y 语义标准与键盘可访问性；
 * 5. 行数严格受控在 400 行以内。
 */

import React, { useEffect, useRef, useState } from 'react';
import {
  Activity,
  GripHorizontal,
  Layers,
  Search,
  Sliders,
  Sparkles,
  Wrench,
  X,
  Zap,
} from 'lucide-react';
import { InSituSkillCard } from './InSituSkillCard';
import { NoiseGaugeLevel } from './inSituSkillPickerTypes';
import { useInSituSkillPickerStore } from './useInSituSkillPickerStore';

export interface InSituWorkflowSkillPickerDrawerProps {
  className?: string;
}

export const InSituWorkflowSkillPickerDrawer: React.FC<
  InSituWorkflowSkillPickerDrawerProps
> = ({ className = '' }) => {
  const {
    searchQuery,
    categoryFilter,
    isDrawerOpen,
    drawerHeight,
    setSearchQuery,
    setCategoryFilter,
    setIsDrawerOpen,
    setDrawerHeight,
    getFilteredSkills,
    getNoiseRating,
    getPreviewNoiseDelta,
    handleIncomingPostMessage,
  } = useInSituSkillPickerStore();

  const [isDraggingSash, setIsDraggingSash] = useState<boolean>(false);
  const dragStartYRef = useRef<number>(0);
  const startHeightRef = useRef<number>(drawerHeight);

  const skills = getFilteredSkills();
  const noiseRating = getNoiseRating();
  const previewDelta = getPreviewNoiseDelta();

  // 跨窗口 postMessage 监听挂载与清理
  useEffect(() => {
    const messageHandler = (e: MessageEvent<unknown>): void => {
      handleIncomingPostMessage(e);
    };

    window.addEventListener('message', messageHandler);
    return () => {
      window.removeEventListener('message', messageHandler);
    };
  }, [handleIncomingPostMessage]);

  // Sash 拖拽高度调整事件监听
  useEffect(() => {
    if (!isDraggingSash) {
      return;
    }

    const handleMouseMove = (e: MouseEvent): void => {
      const deltaY = dragStartYRef.current - e.clientY;
      const nextHeight = startHeightRef.current + deltaY;
      setDrawerHeight(nextHeight);
    };

    const handleMouseUp = (): void => {
      setIsDraggingSash(false);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDraggingSash, setDrawerHeight]);

  const handleSashMouseDown = (e: React.MouseEvent<HTMLButtonElement>): void => {
    dragStartYRef.current = e.clientY;
    startHeightRef.current = drawerHeight;
    setIsDraggingSash(true);
  };

  const getNoiseColorClass = (level: NoiseGaugeLevel): string => {
    if (level === 'optimal') {
      return 'text-emerald-400 border-emerald-500/40 bg-emerald-950/30';
    }
    if (level === 'moderate') {
      return 'text-indigo-400 border-indigo-500/40 bg-indigo-950/30';
    }
    if (level === 'crowded') {
      return 'text-amber-400 border-amber-500/40 bg-amber-950/30';
    }
    return 'text-rose-400 border-rose-500/40 bg-rose-950/30';
  };

  const categories = ['all', '代码开发', '数据分析', '网页检索', '文档提取'];

  return (
    <div
      data-testid="in-situ-skill-picker-drawer-container"
      className={`flex flex-col rounded-xl border border-neutral-800 bg-neutral-950 text-neutral-100 ${className}`}
    >
      {/* 触发控制顶条（当未展开时展示快捷唤出条） */}
      <div className="flex items-center justify-between border-b border-neutral-800/80 px-4 py-3 bg-neutral-900/60">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-indigo-500/30 bg-indigo-950/40 text-indigo-400">
            <Sliders className="h-3.5 w-3.5" />
          </div>
          <div>
            <h3 className="text-xs font-semibold text-neutral-200">
              会话内工作流技能即时探索中心 (In-Situ Skills Hub)
            </h3>
            <p className="text-[11px] text-neutral-400">
              无需离开当前会话，秒级检索并装配智能体扩展能力
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => {
            setIsDrawerOpen(!isDrawerOpen);
          }}
          data-testid="toggle-drawer-btn"
          className="flex items-center gap-1 rounded-lg border border-neutral-800 bg-neutral-900 px-2.5 py-1 text-xs text-neutral-300 hover:bg-neutral-800 hover:text-white transition-colors"
        >
          {isDrawerOpen ? (
            <>
              <X className="h-3.5 w-3.5" />
              <span>收起抽屉</span>
            </>
          ) : (
            <>
              <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
              <span>就地探索技能</span>
            </>
          )}
        </button>
      </div>

      {/* 展开的抽屉实体 */}
      {isDrawerOpen && (
        <div
          data-testid="in-situ-skill-drawer-body"
          style={{ height: `${drawerHeight}px` }}
          className="flex flex-col overflow-hidden transition-all duration-150 ease-out"
        >
          {/* 顶部 Sash 拖拽手柄 */}
          <button
            type="button"
            aria-label="拖拽或上下方向键调整技能抽屉高度"
            data-testid="drawer-sash-handle"
            onMouseDown={handleSashMouseDown}
            onKeyDown={(e) => {
              if (e.key === 'ArrowUp') {
                setDrawerHeight(drawerHeight + 20);
              } else if (e.key === 'ArrowDown') {
                setDrawerHeight(drawerHeight - 20);
              }
            }}
            className={`flex h-4 w-full cursor-row-resize items-center justify-center border-0 border-b border-neutral-800 bg-neutral-900/40 hover:bg-indigo-950/40 transition-colors p-0 focus:outline-none focus:ring-1 focus:ring-indigo-500 ${
              isDraggingSash ? 'bg-indigo-900/40' : ''
            }`}
          >
            <GripHorizontal className="h-3 w-3 text-neutral-500" />
          </button>

          {/* 动作空间噪声看板 (NoiseGauge) */}
          <div
            data-testid="noise-gauge-panel"
            className="flex flex-wrap items-center justify-between gap-3 border-b border-neutral-800/80 bg-neutral-900/40 p-3 text-xs"
          >
            <div className="flex items-center gap-3">
              <span
                data-testid="noise-level-badge"
                className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-medium uppercase font-mono ${getNoiseColorClass(
                  noiseRating.level
                )}`}
              >
                <Activity className="h-3 w-3" />
                <span>动作空间: {noiseRating.level}</span>
              </span>

              <div className="flex items-center gap-2 text-[11px] text-neutral-400 font-mono">
                <span className="flex items-center gap-1">
                  <Zap className="h-3 w-3 text-indigo-400" />
                  <span>总开销: {noiseRating.totalTokens} tok</span>
                </span>
                <span>•</span>
                <span className="flex items-center gap-1">
                  <Wrench className="h-3 w-3 text-neutral-400" />
                  <span>挂载工具: {noiseRating.activeToolsCount} 个</span>
                </span>
              </div>
            </div>

            {/* 增量预估联动指示 */}
            {previewDelta ? (
              <div
                data-testid="noise-preview-delta"
                className="flex items-center gap-1.5 rounded bg-indigo-950/60 px-2 py-0.5 text-[11px] text-indigo-300 ring-1 ring-indigo-500/40 animate-pulse font-mono"
              >
                <span>若挂载将增加: </span>
                <strong>+{previewDelta.deltaTokens} tok</strong>
                <span>(等级: {previewDelta.after.level})</span>
              </div>
            ) : (
              <span className="text-[11px] text-neutral-500">
                {noiseRating.description}
              </span>
            )}
          </div>

          {/* 搜索与分类筛选控制栏 */}
          <div className="flex flex-wrap items-center justify-between gap-2.5 border-b border-neutral-800/60 bg-neutral-950 p-3 text-xs">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-neutral-500" />
              <label htmlFor="skill-search-input" className="sr-only">
                按技能名称、工具或关键词搜索
              </label>
              <input
                id="skill-search-input"
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                }}
                placeholder="搜索技能名称、工具类型或任务场景（如 Excel、爬虫）..."
                className="w-full rounded-md border border-neutral-800 bg-neutral-900 py-1.5 pl-8 pr-3 text-xs text-neutral-200 placeholder-neutral-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div className="flex items-center gap-1 text-xs">
              {categories.map((cat) => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => {
                    setCategoryFilter(cat);
                  }}
                  data-testid={`category-filter-${cat}`}
                  className={`rounded px-2.5 py-1 text-xs transition-colors ${
                    categoryFilter === cat
                      ? 'bg-indigo-950 font-medium text-indigo-300 ring-1 ring-indigo-500/50'
                      : 'bg-neutral-900 text-neutral-400 hover:bg-neutral-800'
                  }`}
                >
                  {cat === 'all' ? '全部领域' : cat}
                </button>
              ))}
            </div>
          </div>

          {/* 技能流卡片列表 */}
          <div
            data-testid="skills-card-grid"
            className="flex-1 overflow-y-auto p-3.5"
          >
            {skills.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {skills.map((skill) => (
                  <InSituSkillCard key={skill.id} skill={skill} />
                ))}
              </div>
            ) : (
              <div
                data-testid="no-skills-found"
                className="flex flex-col items-center justify-center h-full min-h-[160px] text-center text-neutral-500"
              >
                <Layers className="h-6 w-6 stroke-1 text-neutral-600 mb-1" />
                <p className="text-xs">未找到符合条件的技能</p>
                <p className="text-[11px] text-neutral-600">
                  可尝试调整搜索关键词或选择“全部领域”
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
