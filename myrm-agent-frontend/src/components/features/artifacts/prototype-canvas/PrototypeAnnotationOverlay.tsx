/**
 * [INPUT]
 * - prototypeCanvasTypes: PrototypeAnnotation
 * - usePrototypeCanvasStore: usePrototypeCanvasStore
 *
 * [OUTPUT]
 * - PrototypeAnnotationOverlay: Floating visual annotation bubble and drawer list
 *
 * [POS]
 * Click-and-comment annotation overlay for Prototype Canvas (Item 46 P0).
 * Strictly under 280 lines. Zero `any`.
 */

'use client';

import React, { memo, useState, useCallback } from 'react';
import {
  MessageSquare,
  MessageSquarePlus,
  Check,
  Trash2,
  X,
  Send,
  CheckCircle2,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { usePrototypeCanvasStore } from './usePrototypeCanvasStore';

interface SelectedElementPending {
  tag: string;
  selector: string;
  position?: { x: number; y: number };
}

interface PrototypeAnnotationOverlayProps {
  pendingElement: SelectedElementPending | null;
  onClearPending: () => void;
  className?: string;
}

export const PrototypeAnnotationOverlay: React.FC<PrototypeAnnotationOverlayProps> = memo(({
  pendingElement,
  onClearPending,
  className = '',
}) => {
  const t = useTranslations('prototypeCanvas');
  const [commentInput, setCommentInput] = useState('');
  const [showDrawer, setShowDrawer] = useState(false);

  const {
    annotations,
    addAnnotation,
    removeAnnotation,
    toggleResolveAnnotation,
  } = usePrototypeCanvasStore();

  const handleAddComment = useCallback(() => {
    if (!commentInput.trim() || !pendingElement) {
      return;
    }

    addAnnotation({
      elementTag: pendingElement.tag,
      elementSelector: pendingElement.selector,
      comment: commentInput.trim(),
      position: pendingElement.position,
    });

    setCommentInput('');
    onClearPending();
  }, [commentInput, pendingElement, addAnnotation, onClearPending]);

  const unresolvedCount = annotations.filter((a) => !a.resolved).length;

  return (
    <div
      data-testid="prototype-annotation-overlay-root"
      className={`pointer-events-none absolute inset-0 z-20 overflow-hidden ${className}`}
    >
      {/* Floating Prompt Bubble when an element is clicked */}
      {pendingElement && (
        <div
          data-testid="annotation-bubble"
          className="pointer-events-auto absolute top-16 left-1/2 -translate-x-1/2 w-96 max-w-[90vw] bg-white dark:bg-slate-900 rounded-xl shadow-2xl border border-blue-500/80 p-4 flex flex-col gap-2.5 animate-in fade-in slide-in-from-top-2 duration-150"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="p-1 rounded bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400">
                <MessageSquarePlus className="w-3.5 h-3.5" />
              </span>
              <span className="text-xs font-semibold text-slate-800 dark:text-slate-200 truncate">
                {t('selectedElementLabel')}:{' '}
                <code className="text-[11px] font-mono text-blue-600 dark:text-blue-400">
                  {pendingElement.selector}
                </code>
              </span>
            </div>
            <button
              type="button"
              onClick={onClearPending}
              className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-0.5 rounded"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <textarea
            data-testid="annotation-input"
            value={commentInput}
            onChange={(e) => {
              setCommentInput(e.target.value);
            }}
            placeholder={t('commentPlaceholder')}
            rows={2}
            className="w-full text-xs p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/80 text-slate-800 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                handleAddComment();
              }
            }}
          />

          <div className="flex items-center justify-between pt-1">
            <span className="text-[10px] text-slate-400">⌘+Enter 提交</span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onClearPending}
                className="px-2.5 py-1 text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
              >
                {t('cancel')}
              </button>
              <button
                type="button"
                data-testid="submit-annotation-btn"
                onClick={handleAddComment}
                disabled={!commentInput.trim()}
                className="inline-flex items-center gap-1 px-3 py-1 text-xs font-medium bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 dark:disabled:bg-slate-800 text-white rounded-md shadow-xs transition-colors"
              >
                <Send className="w-3 h-3" />
                <span>{t('saveComment')}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Floating Toggle Pill for Annotation Drawer */}
      <div className="pointer-events-auto absolute bottom-4 right-4 z-30">
        <button
          type="button"
          data-testid="toggle-annotations-drawer-btn"
          onClick={() => {
            setShowDrawer(!showDrawer);
          }}
          className="inline-flex items-center gap-1.5 px-3 py-2 bg-slate-900/90 dark:bg-slate-800 text-white text-xs font-medium rounded-full shadow-lg hover:bg-slate-800 backdrop-blur-xs transition-all border border-slate-700/60"
        >
          <MessageSquare className="w-3.5 h-3.5" />
          <span>{t('annotationsList')}</span>
          {unresolvedCount > 0 && (
            <span
              data-testid="unresolved-badge"
              className="px-1.5 py-0.2 bg-amber-500 text-slate-900 text-[10px] font-bold rounded-full"
            >
              {unresolvedCount}
            </span>
          )}
        </button>
      </div>

      {/* Slide-out Annotations Drawer */}
      {showDrawer && (
        <aside
          data-testid="annotations-drawer"
          className="pointer-events-auto absolute top-0 right-0 bottom-0 w-80 max-w-[85vw] bg-white dark:bg-slate-900 border-l border-slate-200 dark:border-slate-800 shadow-2xl flex flex-col z-30 animate-in slide-in-from-right duration-200"
        >
          <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <MessageSquare className="w-4 h-4 text-slate-600 dark:text-slate-300" />
              <h4 className="text-xs font-semibold text-slate-800 dark:text-slate-100">
                {t('annotationsDrawerTitle')} ({annotations.length})
              </h4>
            </div>
            <button
              type="button"
              onClick={() => {
                setShowDrawer(false);
              }}
              className="p-1 rounded text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2.5">
            {annotations.length === 0 ? (
              <div className="p-8 text-center text-slate-400 text-xs">
                {t('noAnnotationsYet')}
              </div>
            ) : (
              annotations.map((anno) => (
                <div
                  key={anno.id}
                  data-testid={`annotation-item-${anno.id}`}
                  className={`p-2.5 rounded-lg border text-xs flex flex-col gap-1.5 transition-all ${
                    anno.resolved
                      ? 'bg-slate-50 dark:bg-slate-900/40 border-slate-200 dark:border-slate-800/80 opacity-60'
                      : 'bg-white dark:bg-slate-800/90 border-slate-200 dark:border-slate-700 shadow-xs'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[10px] text-blue-600 dark:text-blue-400 px-1 py-0.5 rounded bg-blue-50 dark:bg-blue-950/60 truncate max-w-[160px]">
                      {anno.elementSelector}
                    </span>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        data-testid={`resolve-btn-${anno.id}`}
                        onClick={() => {
                          toggleResolveAnnotation(anno.id);
                        }}
                        title={anno.resolved ? t('markUnresolved') : t('markResolved')}
                        className={`p-1 rounded transition-colors ${
                          anno.resolved
                            ? 'text-emerald-600 hover:text-emerald-700'
                            : 'text-slate-400 hover:text-emerald-600'
                        }`}
                      >
                        {anno.resolved ? (
                          <CheckCircle2 className="w-3.5 h-3.5" />
                        ) : (
                          <Check className="w-3.5 h-3.5" />
                        )}
                      </button>
                      <button
                        type="button"
                        data-testid={`delete-btn-${anno.id}`}
                        onClick={() => {
                          removeAnnotation(anno.id);
                        }}
                        title={t('delete')}
                        className="p-1 rounded text-slate-400 hover:text-red-500"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                  <p className="text-slate-700 dark:text-slate-200 whitespace-pre-wrap break-words">
                    {anno.comment}
                  </p>
                </div>
              ))
            )}
          </div>
        </aside>
      )}
    </div>
  );
});

PrototypeAnnotationOverlay.displayName = 'PrototypeAnnotationOverlay';
