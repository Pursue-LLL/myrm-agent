import React, { useRef, useState, useEffect } from 'react';
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  Menu,
  BatteryCharging,
  Clock,
  Cpu,
  FileText,
  X,
  ExternalLink,
} from 'lucide-react';
import { useSkeuomorphicAppStore } from './useSkeuomorphicAppStore';
import {
  calculateWheelAngle,
  calculateAngularStepDelta,
  formatTaskDuration,
  formatTokenUsage,
} from './skeuomorphicAppEngine';

export const ClassicIpodTaskCarouselPlayer: React.FC = () => {
  const {
    artifacts,
    activeItemIndex,
    isDetailOpen,
    autoPlay,
    nextItem,
    prevItem,
    openDetailModal,
    closeDetailModal,
    toggleAutoPlay,
  } = useSkeuomorphicAppStore();

  const currentItem = artifacts[activeItemIndex] || null;
  const wheelRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const previousAngleRef = useRef<number | null>(null);

  // 自动轮播支持
  useEffect(() => {
    if (!autoPlay || artifacts.length <= 1) {
      return;
    }
    const timer = setInterval(() => {
      nextItem();
    }, 3000);
    return () => clearInterval(timer);
  }, [autoPlay, artifacts.length, nextItem]);

  // 转盘拖动与滑动交互处理
  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!wheelRef.current) {
      return;
    }
    const rect = wheelRef.current.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    const initialAngle = calculateWheelAngle(e.clientX, e.clientY, centerX, centerY);
    previousAngleRef.current = initialAngle;
    setIsDragging(true);
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging || !wheelRef.current || previousAngleRef.current === null) {
      return;
    }
    const rect = wheelRef.current.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    const currentAngle = calculateWheelAngle(e.clientX, e.clientY, centerX, centerY);

    const { stepDelta, remainingAngle } = calculateAngularStepDelta(
      currentAngle,
      previousAngleRef.current,
      24
    );

    if (stepDelta > 0) {
      for (let i = 0; i < stepDelta; i++) {
        nextItem();
      }
      previousAngleRef.current = currentAngle - remainingAngle;
    } else if (stepDelta < 0) {
      for (let i = 0; i < Math.abs(stepDelta); i++) {
        prevItem();
      }
      previousAngleRef.current = currentAngle - remainingAngle;
    }
  };

  const handlePointerUp = () => {
    setIsDragging(false);
    previousAngleRef.current = null;
  };

  return (
    <div
      data-testid="classic-ipod-player"
      className="relative flex flex-col items-center justify-between w-72 h-[480px] bg-gradient-to-b from-slate-200 via-slate-300 to-slate-400 border border-slate-400 rounded-[32px] p-5 shadow-2xl select-none"
    >
      {/* 顶部灰阶点阵 LCD 屏幕 */}
      <div className="w-full h-44 bg-[#9ba792] border-2 border-slate-700/60 rounded-lg p-2.5 shadow-inner font-mono text-slate-800 flex flex-col justify-between overflow-hidden">
        {/* LCD 状态栏 */}
        <div className="flex items-center justify-between border-b border-slate-700/40 pb-1 text-[11px] font-bold">
          <span className="truncate max-w-[120px]">
            {currentItem?.stageName || 'Myrm Codex'}
          </span>
          <div className="flex items-center gap-1.5">
            {autoPlay && <Play className="w-3 h-3 text-slate-800 animate-pulse" />}
            <span className="text-[10px]">
              {artifacts.length > 0 ? `${activeItemIndex + 1}/${artifacts.length}` : '0/0'}
            </span>
            <BatteryCharging className="w-3.5 h-3.5 text-slate-800" />
          </div>
        </div>

        {/* LCD 内容主体 */}
        <div className="my-auto flex flex-col gap-1">
          <p className="text-xs font-bold leading-tight line-clamp-2">
            {currentItem?.taskTitle || '无进行中任务'}
          </p>
          <p className="text-[10px] text-slate-700 line-clamp-2 leading-relaxed">
            {currentItem?.summary || '通过下方拟物化轮盘旋转快速翻阅工件'}
          </p>
        </div>

        {/* LCD 底部进度指示条与性能度量 */}
        <div className="flex items-center justify-between border-t border-slate-700/40 pt-1 text-[9px] font-semibold text-slate-700">
          <div className="flex items-center gap-1">
            <Clock className="w-2.5 h-2.5" />
            <span>{currentItem ? formatTaskDuration(currentItem.durationMs) : '0s'}</span>
          </div>
          <div className="flex items-center gap-1">
            <Cpu className="w-2.5 h-2.5" />
            <span>{currentItem ? formatTokenUsage(currentItem.tokensUsed) : '0 T'}</span>
          </div>
        </div>
      </div>

      {/* 经典 Click Wheel 机械触控轮盘 */}
      <div
        ref={wheelRef}
        data-testid="ipod-click-wheel"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        className="relative w-44 h-44 rounded-full bg-slate-100 border border-slate-300 shadow-md flex items-center justify-center cursor-grab active:cursor-grabbing touch-none"
      >
        {/* MENU 上方按钮 */}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            openDetailModal();
          }}
          className="absolute top-2 text-slate-500 hover:text-slate-800 transition-colors"
          title="打开工件详情"
          aria-label="菜单"
        >
          <Menu className="w-4 h-4" />
        </button>

        {/* 上一个 / 快退 左侧按钮 */}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            prevItem();
          }}
          className="absolute left-2 text-slate-500 hover:text-slate-800 transition-colors"
          title="上一个任务工件"
          aria-label="上一个任务工件"
        >
          <SkipBack className="w-4 h-4" />
        </button>

        {/* 下一个 / 快进 右侧按钮 */}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            nextItem();
          }}
          className="absolute right-2 text-slate-500 hover:text-slate-800 transition-colors"
          title="下一个任务工件"
          aria-label="下一个任务工件"
        >
          <SkipForward className="w-4 h-4" />
        </button>

        {/* 播放/暂停 下方按钮 */}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            toggleAutoPlay();
          }}
          className="absolute bottom-2 text-slate-500 hover:text-slate-800 transition-colors"
          title={autoPlay ? '暂停自动轮播' : '开始自动轮播'}
          aria-label={autoPlay ? '暂停自动轮播' : '开始自动轮播'}
        >
          {autoPlay ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
        </button>

        {/* 中央 SELECT 圆形按钮 */}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            openDetailModal();
          }}
          className="w-16 h-16 rounded-full bg-gradient-to-b from-slate-200 to-slate-300 border border-slate-400 shadow-inner hover:brightness-95 active:scale-95 transition-all flex items-center justify-center text-xs font-bold text-slate-700"
          title="展开工件成果"
          aria-label="查看详情"
        >
          SELECT
        </button>
      </div>

      {/* 工件成果弹窗详情视窗 */}
      {isDetailOpen && currentItem && (
        <dialog
          open
          aria-modal="true"
          className="absolute inset-0 bg-slate-900/90 backdrop-blur-sm rounded-[32px] p-5 flex flex-col justify-between text-slate-100 z-50 animate-in fade-in zoom-in-95 duration-150 border-0"
        >
          <div className="flex items-center justify-between border-b border-slate-700 pb-2">
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-emerald-400" />
              <span className="text-xs font-semibold text-slate-200 truncate max-w-[170px]">
                {currentItem.taskTitle}
              </span>
            </div>
            <button
              type="button"
              onClick={closeDetailModal}
              className="text-slate-400 hover:text-white transition-colors"
              aria-label="关闭详情"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto my-3 text-xs space-y-2 font-mono text-slate-300">
            <div>
              <span className="text-slate-500 text-[10px]">负责人：</span>
              <span className="text-slate-200">{currentItem.authorAgent}</span>
            </div>
            <div>
              <span className="text-slate-500 text-[10px]">交付阶段：</span>
              <span className="text-slate-200">{currentItem.stageName}</span>
            </div>
            <div>
              <span className="text-slate-500 text-[10px]">产物摘要：</span>
              <p className="mt-0.5 text-slate-200 text-xs leading-relaxed font-sans">
                {currentItem.summary}
              </p>
            </div>
            {currentItem.codeSnippet && (
              <div className="bg-slate-950 p-2 rounded border border-slate-800 text-[11px] overflow-x-auto text-emerald-300">
                <code>{currentItem.codeSnippet}</code>
              </div>
            )}
          </div>

          <div className="border-t border-slate-700 pt-2 flex items-center justify-between text-[11px]">
            <span className="text-slate-400 font-mono">
              {formatTokenUsage(currentItem.tokensUsed)}
            </span>
            <button
              type="button"
              onClick={closeDetailModal}
              className="inline-flex items-center gap-1 px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs transition-colors font-sans"
            >
              <span>收起工件</span>
              <ExternalLink className="w-3 h-3" />
            </button>
          </div>
        </dialog>
      )}
    </div>
  );
};
