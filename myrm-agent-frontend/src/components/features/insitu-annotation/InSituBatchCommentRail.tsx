import React from 'react';
import {
  Package,
  Layers,
  Trash2,
  Send,
  Sliders,
  CheckCircle2,
  ChevronRight,
  X,
} from 'lucide-react';
import { useInsituAnnotationStore } from './useInsituAnnotationStore';
import { buildBatchAnnotationPayload } from './insituAnnotationEngine';
import { BatchAnnotationPayload } from './insituAnnotationTypes';

interface InSituBatchCommentRailProps {
  onBatchDispatch?: (payload: BatchAnnotationPayload) => void;
}

export const InSituBatchCommentRail: React.FC<InSituBatchCommentRailProps> = ({
  onBatchDispatch,
}) => {
  const {
    artifactId,
    comments,
    stylePatches,
    activeCommentId,
    setActiveCommentId,
    removeCommentPin,
    removeStylePatch,
    isRailOpen,
    toggleRail,
    clearAll,
  } = useInsituAnnotationStore();

  if (!isRailOpen) {
    return null;
  }

  const handleDispatch = () => {
    const payload = buildBatchAnnotationPayload(
      artifactId,
      comments,
      stylePatches
    );
    if (onBatchDispatch) {
      onBatchDispatch(payload);
    }
  };

  const totalModifications = comments.length + stylePatches.length;

  return (
    <aside
      data-testid="insitu-batch-comment-rail"
      aria-label="画布修改与批注汇总侧栏"
      className="w-72 bg-slate-950/95 border-l border-slate-800 p-3.5 flex flex-col justify-between h-full select-none text-xs text-slate-200 shadow-xl"
    >
      <div className="space-y-3 flex-1 overflow-y-auto pr-1">
        {/* 顶部标题与折叠 */}
        <div className="flex items-center justify-between pb-2 border-b border-slate-800">
          <div className="flex items-center gap-1.5 font-bold text-slate-200">
            <Package className="w-4 h-4 text-indigo-400" />
            <span>批注与修改清单</span>
          </div>

          <div className="flex items-center gap-1">
            <span className="px-1.5 py-0.5 rounded font-mono text-[10px] bg-indigo-950 text-indigo-300 border border-indigo-800">
              {totalModifications} 项
            </span>
            <button
              type="button"
              onClick={toggleRail}
              className="p-1 rounded text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              title="收起侧栏"
              aria-label="收起侧栏"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* 批注打点列表 */}
        <div className="space-y-1.5">
          <div className="flex items-center gap-1 text-[11px] font-mono text-slate-400">
            <Layers className="w-3 h-3 text-slate-500" />
            <span>画布悬浮批注 ({comments.length})</span>
          </div>

          {comments.length === 0 ? (
            <div className="p-2.5 rounded-xl border border-dashed border-slate-800 text-slate-500 text-center text-[11px]">
              点击画布任意元素即可打标批注
            </div>
          ) : (
            comments.map((c) => {
              const isSelected = activeCommentId === c.id;
              return (
                <div
                  key={c.id}
                  className={`p-2 rounded-xl border transition-all ${
                    isSelected
                      ? 'bg-indigo-950/60 border-indigo-500 shadow-sm'
                      : 'bg-slate-900/50 border-slate-800'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => setActiveCommentId(c.id)}
                      className="flex items-center gap-1.5 text-left font-mono font-semibold text-slate-300 hover:text-indigo-300"
                    >
                      <span className="w-4 h-4 rounded-full bg-indigo-600 text-white text-[10px] flex items-center justify-center">
                        {c.index}
                      </span>
                      <span>&lt;{c.targetTag}&gt;</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => removeCommentPin(c.id)}
                      className="p-1 rounded text-slate-500 hover:text-rose-400 transition-colors"
                      title="删除批注"
                      aria-label="删除"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>

                  <p className="mt-1 text-[11px] text-slate-400 line-clamp-2 leading-tight">
                    {c.commentText || '（暂无输入修改诉求）'}
                  </p>
                </div>
              );
            })
          )}
        </div>

        {/* 就地样式补丁列表 */}
        {stylePatches.length > 0 && (
          <div className="space-y-1.5 pt-2 border-t border-slate-800/80">
            <div className="flex items-center gap-1 text-[11px] font-mono text-slate-400">
              <Sliders className="w-3 h-3 text-indigo-400" />
              <span>就地样式补丁 ({stylePatches.length})</span>
            </div>

            {stylePatches.map((patch) => (
              <div
                key={patch.selector}
                className="p-2 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center justify-between text-[11px]"
              >
                <div className="min-w-0 flex-1">
                  <div className="font-mono text-slate-300 font-semibold truncate">
                    {patch.selector}
                  </div>
                  <div className="text-[10px] text-slate-500 truncate">
                    {patch.textContent ? `文本: "${patch.textContent}" ` : ''}
                    {patch.color ? `色: ${patch.color} ` : ''}
                    {patch.fontSize ? `字号: ${patch.fontSize} ` : ''}
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => removeStylePatch(patch.selector)}
                  className="p-1 rounded text-slate-500 hover:text-rose-400 transition-colors shrink-0 ml-1"
                  title="撤销此补丁"
                  aria-label="撤销补丁"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 底部操作区 */}
      <div className="pt-3 border-t border-slate-800 space-y-2">
        <button
          type="button"
          onClick={handleDispatch}
          disabled={totalModifications === 0}
          className="w-full flex items-center justify-center gap-1.5 py-2 px-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-xs transition-colors shadow-md cursor-pointer"
        >
          <Send className="w-3.5 h-3.5" />
          <span>打包提交全部批注 ({totalModifications})</span>
        </button>

        {totalModifications > 0 && (
          <button
            type="button"
            onClick={clearAll}
            className="w-full py-1 text-center text-[10px] text-slate-500 hover:text-slate-300 transition-colors font-mono"
          >
            清空所有未提交批注
          </button>
        )}
      </div>
    </aside>
  );
};
