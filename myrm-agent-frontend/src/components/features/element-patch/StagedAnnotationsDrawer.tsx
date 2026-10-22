/* oxlint-disable jsx-a11y/prefer-tag-over-role */
import React, { useState } from 'react';
import {
  X,
  Package,
  Trash2,
  Send,
  PlusCircle,
  Crosshair,
  ShieldCheck,
  CheckCircle,
  AlertCircle,
  Edit2,
  Check,
} from 'lucide-react';
import { useElementPatchStore } from './useElementPatchStore';
import { formatAnnotationStatus } from './elementPatchEngine';
import { StagedBatchPayload } from './elementPatchTypes';
import { REVEAL_ON_HOVER } from '@/lib/utils/a11y';

export interface StagedAnnotationsDrawerProps {
  artifactId: string;
  onDispatchBatch?: (payload: StagedBatchPayload) => void;
  className?: string;
}

export const StagedAnnotationsDrawer: React.FC<StagedAnnotationsDrawerProps> = ({
  artifactId,
  onDispatchBatch,
  className = '',
}) => {
  const {
    stagedAnnotations,
    isDrawerOpen,
    selectedAnnotationId,
    isPickingElement,
    toggleDrawer,
    removeAnnotation,
    clearStaged,
    packageAndDispatch,
    startPicking,
    selectAnnotation,
    updateAnnotationInstruction,
  } = useElementPatchStore();

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState('');

  if (!isDrawerOpen || stagedAnnotations.length === 0) {
    return null;
  }

  const handleStartEdit = (id: string, currentInstruction: string) => {
    setEditingId(id);
    setEditText(currentInstruction);
  };

  const handleSaveEdit = (id: string) => {
    if (editText.trim()) {
      updateAnnotationInstruction(id, editText.trim());
    }
    setEditingId(null);
    setEditText('');
  };

  const handleDispatch = () => {
    const payload = packageAndDispatch(artifactId);
    if (payload && onDispatchBatch) {
      onDispatchBatch(payload);
    }
  };

  return (
    <aside
      data-testid="staged-annotations-drawer"
      aria-label="批注暂存箱"
      className={`fixed bottom-0 right-0 z-40 w-full sm:w-[460px] max-h-[80vh] bg-zinc-900/98 backdrop-blur-xl border-t sm:border-l border-zinc-800 rounded-t-2xl sm:rounded-tl-2xl shadow-2xl flex flex-col font-sans transition-all duration-300 ${className}`}
    >
      {/* 1. 抽屉顶部标题与操作 */}
      <header className="px-4 py-3 border-b border-zinc-800 bg-zinc-950/70 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <Package className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <h3 className="text-xs font-bold text-zinc-100">批注暂存箱</h3>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded-full bg-indigo-600 text-white font-semibold">
                {stagedAnnotations.length} 项
              </span>
            </div>
            <p className="text-[10px] text-zinc-400">
              连续点选打标 · 一键打包合并下发防代码漂移
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={clearStaged}
            aria-label="清空暂存箱"
            title="清空暂存箱"
            className="p-1.5 rounded-lg text-zinc-400 hover:text-red-400 hover:bg-zinc-800 transition-colors"
          >
            <Trash2 className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => {
              toggleDrawer(false);
            }}
            aria-label="收起暂存箱"
            title="收起"
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* 2. 手术刀防漂移说明条 */}
      <div className="px-3.5 py-2 bg-indigo-950/30 border-b border-indigo-500/20 flex items-center gap-1.5 text-[11px] text-indigo-300 font-mono">
        <ShieldCheck className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
        <span>外科手术式精准局部替换 · 全页其余组件 100% 保持不变</span>
      </div>

      {/* 3. 暂存批注列表 */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-2.5">
        {stagedAnnotations.map((ann, idx) => {
          const statusTheme = formatAnnotationStatus(ann.status);
          const isSelected = selectedAnnotationId === ann.id;
          const isEditing = editingId === ann.id;

          return (
            // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role -- clickable card with nested action buttons
            <div
              key={ann.id}
              role="button"
              tabIndex={0}
              onClick={() => {
                selectAnnotation(ann.id);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  selectAnnotation(ann.id);
                }
              }}
              className={`p-3 rounded-xl border transition-all cursor-pointer ${
                isSelected
                  ? 'bg-zinc-950 border-indigo-500/50 shadow-md'
                  : 'bg-zinc-950/60 border-zinc-800 hover:border-zinc-750'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-1.5 truncate">
                  <span className="w-5 h-5 rounded-full bg-indigo-600 text-white text-[11px] font-bold flex items-center justify-center shrink-0">
                    {idx + 1}
                  </span>
                  <span className="font-mono text-xs font-semibold text-zinc-200 truncate">
                    {ann.selector}
                  </span>
                </div>

                <div className="flex items-center gap-1 shrink-0">
                  <span
                    className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${statusTheme.bg} ${statusTheme.text} ${statusTheme.border}`}
                  >
                    {statusTheme.label}
                  </span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeAnnotation(ann.id);
                    }}
                    aria-label={`移除第 ${idx + 1} 项批注`}
                    title="移除此项"
                    className="p-1 rounded text-zinc-500 hover:text-red-400 hover:bg-zinc-800 transition-colors"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              {/* 原节点片段 */}
              {ann.elementTextSnippet && (
                <div className="mt-1 text-[10px] text-zinc-500 font-mono truncate">
                  原文字: &quot;{ann.elementTextSnippet}&quot;
                </div>
              )}

              {/* 批注说明或内联编辑 */}
              <div className="mt-2 text-xs leading-relaxed text-zinc-300">
                {isEditing ? (
                  <div className="flex items-center gap-1.5">
                    <input
                      type="text"
                      value={editText}
                      onChange={(e) => {
                        setEditText(e.target.value);
                      }}
                      className="flex-1 px-2 py-1 text-xs bg-zinc-900 border border-indigo-500 rounded text-zinc-100 focus:outline-none"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        handleSaveEdit(ann.id);
                      }}
                      className="p-1 rounded bg-indigo-600 text-white"
                      title="保存修改"
                    >
                      <Check className="w-3 h-3" />
                    </button>
                  </div>
                ) : (
                  <div className="flex items-start justify-between gap-1 group">
                    <p className="flex-1">{ann.instruction}</p>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleStartEdit(ann.id, ann.instruction);
                      }}
                      className={`${REVEAL_ON_HOVER} p-1 text-zinc-400 hover:text-zinc-200 transition-opacity`}
                      title="修改批注"
                    >
                      <Edit2 className="w-3 h-3" />
                    </button>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* 4. 底部操作区 */}
      <footer className="p-3 border-t border-zinc-800 bg-zinc-950/80 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={startPicking}
          disabled={isPickingElement}
          className="flex items-center gap-1 px-3 py-2 text-xs font-medium text-zinc-300 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded-xl transition-colors disabled:opacity-40"
        >
          <Crosshair className="w-3.5 h-3.5 text-indigo-400" />
          <span>{isPickingElement ? '正在拾取节点...' : '继续拾取打点'}</span>
        </button>

        <button
          type="button"
          onClick={handleDispatch}
          className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl shadow-lg transition-colors"
        >
          <Send className="w-3.5 h-3.5" />
          <span>一键打包发送 ({stagedAnnotations.length} 处修改)</span>
        </button>
      </footer>
    </aside>
  );
};
