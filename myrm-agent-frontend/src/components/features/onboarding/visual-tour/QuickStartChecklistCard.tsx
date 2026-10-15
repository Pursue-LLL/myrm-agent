import React, { useMemo } from 'react';
import {
  Rocket,
  CheckCircle2,
  Circle,
  ChevronDown,
  ChevronUp,
  X,
  RotateCcw,
  Trophy,
  ArrowUpRight,
} from 'lucide-react';
import { useVisualTourStore } from './useVisualTourStore';
import { calculateChecklistProgress } from './visualTourEngine';

export const QuickStartChecklistCard: React.FC = () => {
  const {
    checklistItems,
    isChecklistCollapsed,
    isChecklistDismissed,
    toggleChecklistItem,
    setChecklistCollapsed,
    setChecklistDismissed,
    resetOnboardingState,
  } = useVisualTourStore();

  const progress = useMemo(() => {
    return calculateChecklistProgress(checklistItems);
  }, [checklistItems]);

  if (isChecklistDismissed) {
    return null;
  }

  if (isChecklistCollapsed) {
    return (
      <div className="fixed bottom-5 right-5 z-40">
        <button
          type="button"
          onClick={() => {
            setChecklistCollapsed(false);
          }}
          className="flex items-center gap-2 rounded-full border border-indigo-500/30 bg-slate-900/90 px-3.5 py-2 text-xs font-medium text-slate-100 shadow-xl backdrop-blur-md hover:border-indigo-400 hover:bg-slate-800 transition-all duration-200"
          aria-label="展开新手开箱核对单"
        >
          <Rocket className="h-4 w-4 text-indigo-400" />
          <span>新手开箱指南</span>
          <span className="rounded-full bg-indigo-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-300">
            {progress.percentage}%
          </span>
          <ChevronUp className="h-3.5 w-3.5 text-slate-400" />
        </button>
      </div>
    );
  }

  return (
    <div
      data-testid="quickstart-checklist-card"
      className="fixed bottom-5 right-5 z-40 w-84 rounded-2xl border border-slate-700/80 bg-slate-900/95 p-4 shadow-2xl backdrop-blur-md text-slate-100 animate-in slide-in-from-bottom-5 duration-200"
    >
      {/* 头部标题与控制按钮 */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/20 text-indigo-400">
            <Rocket className="h-4 w-4" />
          </div>
          <div>
            <h4 className="text-xs font-semibold text-slate-100">新手 3 分钟极速上手</h4>
            <p className="text-[10px] text-slate-400">已完成 {progress.completedCount} / {progress.totalCount} 项</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => {
              setChecklistCollapsed(true);
            }}
            aria-label="折叠清单"
            className="rounded-md p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
          >
            <ChevronDown className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => {
              setChecklistDismissed(true);
            }}
            aria-label="关闭清单"
            className="rounded-md p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* 进度条 */}
      <div className="my-3">
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
          <div
            className="h-full bg-gradient-to-r from-indigo-500 to-emerald-400 transition-all duration-300"
            style={{ width: `${progress.percentage}%` }}
          />
        </div>
      </div>

      {/* 清单列表 */}
      {progress.isAllCompleted ? (
        <div className="my-3 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3 text-center">
          <div className="mx-auto flex h-8 w-8 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400">
            <Trophy className="h-4 w-4" />
          </div>
          <p className="mt-1.5 text-xs font-semibold text-emerald-300">所有起步任务已全部达成！</p>
          <p className="mt-0.5 text-[10px] text-slate-300">您已解锁 Myrm 通用 AI 伙伴全部潜能</p>
        </div>
      ) : (
        <div className="space-y-2.5 my-2">
          {checklistItems.map((item) => {
            return (
              <div
                key={item.id}
                className="group flex items-start gap-2.5 rounded-lg border border-slate-800/80 bg-slate-950/40 p-2.5 transition-colors hover:border-slate-700 hover:bg-slate-800/30"
              >
                <button
                  type="button"
                  onClick={() => {
                    toggleChecklistItem(item.id);
                  }}
                  aria-label={item.completed ? `已打卡：${item.title}` : `点击打卡：${item.title}`}
                  className="mt-0.5 shrink-0 text-slate-400 transition-colors hover:text-indigo-400"
                >
                  {item.completed ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                  ) : (
                    <Circle className="h-4 w-4 text-slate-500" />
                  )}
                </button>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span
                      className={`text-xs font-medium truncate ${
                        item.completed ? 'text-slate-400 line-through' : 'text-slate-200'
                      }`}
                    >
                      {item.title}
                    </span>
                    {item.actionUrl && (
                      <a
                        href={item.actionUrl}
                        className="text-[10px] text-indigo-400 hover:underline inline-flex items-center gap-0.5 shrink-0"
                      >
                        前往
                        <ArrowUpRight className="h-2.5 w-2.5" />
                      </a>
                    )}
                  </div>
                  <p className="mt-0.5 text-[10px] text-slate-400 leading-relaxed">
                    {item.description}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* 底部重置与引导重温 */}
      <div className="pt-2 flex items-center justify-between text-[11px] border-t border-slate-800/80">
        <button
          type="button"
          onClick={resetOnboardingState}
          className="flex items-center gap-1 text-slate-400 hover:text-indigo-400 transition-colors"
        >
          <RotateCcw className="h-3 w-3" />
          <span>重温全景漫游</span>
        </button>
        <button
          type="button"
          onClick={() => {
            setChecklistDismissed(true);
          }}
          className="text-slate-500 hover:text-slate-300 transition-colors"
        >
          暂不提示
        </button>
      </div>
    </div>
  );
};
