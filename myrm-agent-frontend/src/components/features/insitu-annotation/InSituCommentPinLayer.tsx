import React from 'react';
import { MessageSquare, Trash2, X } from 'lucide-react';
import { useInsituAnnotationStore } from './useInsituAnnotationStore';

export const InSituCommentPinLayer: React.FC = () => {
  const {
    comments,
    activeCommentId,
    setActiveCommentId,
    updateCommentPinText,
    removeCommentPin,
  } = useInsituAnnotationStore();

  return (
    <div
      data-testid="insitu-comment-pin-layer"
      className="absolute inset-0 pointer-events-none z-30 overflow-hidden"
    >
      {comments.map((pin) => {
        const isActive = activeCommentId === pin.id;

        return (
          <div
            key={pin.id}
            style={{ left: `${pin.x}px`, top: `${pin.y}px` }}
            className="absolute -translate-x-1/2 -translate-y-1/2 pointer-events-auto"
          >
            {/* 批注序号气泡按钮 */}
            <button
              type="button"
              onClick={() => setActiveCommentId(isActive ? null : pin.id)}
              data-testid={`comment-pin-badge-${pin.index}`}
              className={`w-7 h-7 rounded-full flex items-center justify-center font-bold text-xs font-mono shadow-lg transition-transform border cursor-pointer ${
                isActive
                  ? 'bg-amber-500 border-amber-300 text-slate-950 scale-110 ring-2 ring-amber-400/50'
                  : 'bg-indigo-600 border-indigo-400 text-white hover:scale-105'
              }`}
              title={`批注 #${pin.index}: ${pin.commentText || '未输入诉求'}`}
              aria-label={`批注 #${pin.index}`}
            >
              <span>{pin.index}</span>
            </button>

            {/* 展开的批注详情悬浮卡片 */}
            {isActive && (
              <div
                data-testid={`comment-pin-popover-${pin.index}`}
                className="absolute left-1/2 -translate-x-1/2 top-9 z-40 w-64 bg-slate-900/95 backdrop-blur-md border border-slate-700/80 rounded-2xl p-3 shadow-2xl text-xs text-slate-200 animate-in fade-in zoom-in-95 duration-150"
              >
                <div className="flex items-center justify-between pb-1.5 mb-2 border-b border-slate-800">
                  <div className="flex items-center gap-1.5 font-semibold text-slate-300 text-[11px]">
                    <MessageSquare className="w-3.5 h-3.5 text-indigo-400" />
                    <span>批注 #{pin.index}</span>
                    <span className="font-mono text-slate-500 text-[10px]">
                      &lt;{pin.targetTag}&gt;
                    </span>
                  </div>

                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => removeCommentPin(pin.id)}
                      className="p-1 rounded hover:bg-rose-900/40 text-slate-400 hover:text-rose-300 transition-colors"
                      title="删除此批注"
                      aria-label="删除批注"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveCommentId(null)}
                      className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
                      title="收起"
                      aria-label="关闭"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                </div>

                <textarea
                  rows={2}
                  value={pin.commentText}
                  onChange={(e) => updateCommentPinText(pin.id, e.target.value)}
                  placeholder="在此输入您的具体修改诉求..."
                  className="w-full px-2.5 py-1.5 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 resize-none font-mono"
                />

                <div className="mt-2 flex items-center justify-between text-[10px] text-slate-500 font-mono">
                  <span>{pin.createdAt}</span>
                  <span className="text-indigo-400">自动同步至右侧汇总</span>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};
