/**
 * [INPUT]
 * - variantId: string
 * - chatId: string
 * - annotations: VisualAnnotationItem[]
 * - isAnnotating: boolean
 * - onAnnotationAdded?: () => void
 *
 * [OUTPUT]
 * - VisualAnnotationOverlay: Interactive canvas drawing overlay for placing bounding-box visual annotations
 *
 * [POS]
 * Visual annotation interactive component for Multi-Turn UI Design Visual Alignment (Item 39 P0).
 * Strictly under 240 lines. Zero `any`.
 */

import React, { useState, useRef, useCallback } from "react";
import { MessageSquare, Check, X, Tag } from "lucide-react";
import { useTranslations } from "next-intl";
import type { VisualAnnotationItem } from "./uiAlignmentTypes";
import { useUiAlignmentStore } from "./useUiAlignmentStore";

interface VisualAnnotationOverlayProps {
  variantId: string;
  chatId: string;
  annotations: VisualAnnotationItem[];
  isAnnotating: boolean;
}

interface DraftBox {
  startX: number;
  startY: number;
  currX: number;
  currY: number;
}

export const VisualAnnotationOverlay: React.FC<VisualAnnotationOverlayProps> = ({
  variantId,
  chatId,
  annotations,
  isAnnotating,
}) => {
  const t = useTranslations("uiAlignment");
  const addAnnotation = useUiAlignmentStore((state) => state.addAnnotation);

  const containerRef = useRef<HTMLDivElement>(null);
  const [draft, setDraft] = useState<DraftBox | null>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [pendingBox, setPendingBox] = useState<{
    x: number;
    y: number;
    width: number;
    height: number;
  } | null>(null);
  const [comment, setComment] = useState("");
  const [label, setLabel] = useState("visual_feedback");

  const getPercentages = useCallback((e: React.MouseEvent<HTMLElement>) => {
    if (!containerRef.current) {
      return { x: 0, y: 0 };
    }
    const rect = containerRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100));
    const y = Math.max(0, Math.min(100, ((e.clientY - rect.top) / rect.height) * 100));
    return { x, y };
  }, []);

  const handleMouseDown = (e: React.MouseEvent<HTMLElement>) => {
    if (!isAnnotating || pendingBox) {
      return;
    }
    const { x, y } = getPercentages(e);
    setIsDrawing(true);
    setDraft({ startX: x, startY: y, currX: x, currY: y });
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLElement>) => {
    if (!isDrawing || !draft) {
      return;
    }
    const { x, y } = getPercentages(e);
    setDraft((prev) => (prev ? { ...prev, currX: x, currY: y } : null));
  };

  const handleMouseUp = () => {
    if (!isDrawing || !draft) {
      return;
    }
    setIsDrawing(false);
    const x = Math.min(draft.startX, draft.currX);
    const y = Math.min(draft.startY, draft.currY);
    const width = Math.max(draft.startX, draft.currX) - x;
    const height = Math.max(draft.startY, draft.currY) - y;

    // Minimum threshold for box creation, else a small default click target
    const finalW = width < 2 ? 15 : width;
    const finalH = height < 2 ? 10 : height;

    setPendingBox({ x, y, width: finalW, height: finalH });
    setDraft(null);
  };

  const handleSaveAnnotation = async () => {
    if (!pendingBox || !comment.trim()) {
      return;
    }
    await addAnnotation(chatId, variantId, {
      x: pendingBox.x,
      y: pendingBox.y,
      width: pendingBox.width,
      height: pendingBox.height,
      comment: comment.trim(),
      label: label.trim(),
    });
    setPendingBox(null);
    setComment("");
  };

  const handleCancelPending = () => {
    setPendingBox(null);
    setComment("");
  };

  return (
    <section
      ref={containerRef}
      aria-label="Visual Annotation Canvas"
      className="absolute inset-0 z-20 pointer-events-none"
    >
      {/* Interactive Drawing Capture Surface */}
      {isAnnotating && !pendingBox && (
        <button
          type="button"
          aria-label="Interactive Drawing Canvas Surface"
          className="absolute inset-0 cursor-crosshair select-none bg-indigo-950/10 pointer-events-auto border-none p-0 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setDraft(null);
            }
          }}
        />
      )}

      {/* Existing Annotations */}
      {annotations.map((item, idx) => (
        <div
          key={item.annotation_id || `anno-${idx}`}
          className="absolute border-2 border-indigo-500 bg-indigo-500/20 rounded pointer-events-auto group transition-all"
          style={{
            left: `${item.x}%`,
            top: `${item.y}%`,
            width: `${item.width}%`,
            height: `${item.height}%`,
          }}
        >
          <div className="absolute -top-3 -left-3 flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-indigo-600 text-white text-[10px] font-semibold shadow-sm">
            <MessageSquare className="w-2.5 h-2.5" />
            <span>{idx + 1}</span>
          </div>
          {/* Hover Tooltip */}
          <div className="hidden group-hover:block absolute left-0 top-full mt-1 z-30 min-w-[180px] p-2 bg-zinc-900 border border-zinc-700 rounded text-xs text-zinc-100 shadow-xl backdrop-blur-md">
            <div className="flex items-center gap-1 text-[10px] text-indigo-400 font-mono mb-1">
              <Tag className="w-2.5 h-2.5" />
              <span>{item.label}</span>
            </div>
            <p className="leading-snug">{item.comment}</p>
          </div>
        </div>
      ))}

      {/* Currently Drawing Box */}
      {isDrawing && draft && (
        <div
          className="absolute border-2 border-dashed border-amber-400 bg-amber-400/20 rounded pointer-events-none"
          style={{
            left: `${Math.min(draft.startX, draft.currX)}%`,
            top: `${Math.min(draft.startY, draft.currY)}%`,
            width: `${Math.abs(draft.currX - draft.startX)}%`,
            height: `${Math.abs(draft.currY - draft.startY)}%`,
          }}
        />
      )}

      {/* Pending Input Dialog */}
      {pendingBox && (
        <section
          aria-label={t("addAnnotationTitle")}
          className="absolute z-40 p-3 bg-zinc-900/95 border border-indigo-500/60 rounded-lg shadow-2xl backdrop-blur-md w-72 text-zinc-100 pointer-events-auto"
          style={{
            left: `${Math.min(pendingBox.x + pendingBox.width + 2, 70)}%`,
            top: `${Math.min(pendingBox.y, 70)}%`,
          }}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold flex items-center gap-1 text-indigo-300">
              <MessageSquare className="w-3.5 h-3.5" />
              {t("addAnnotationTitle")}
            </span>
            <button
              type="button"
              onClick={handleCancelPending}
              className="text-zinc-400 hover:text-zinc-200"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder={t("commentPlaceholder")}
            rows={3}
            className="w-full text-xs p-2 rounded bg-zinc-950 border border-zinc-700 text-zinc-100 focus:outline-none focus:border-indigo-500 resize-none mb-2"
          />
          <div className="flex items-center gap-1 mb-3">
            <select
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="text-[11px] bg-zinc-950 border border-zinc-700 rounded px-2 py-1 text-zinc-300 focus:outline-none"
            >
              <option value="visual_feedback">{t("labelVisual")}</option>
              <option value="typography">{t("labelTypography")}</option>
              <option value="layout">{t("labelLayout")}</option>
              <option value="accessibility">{t("labelA11y")}</option>
            </select>
          </div>
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={handleCancelPending}
              className="px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 rounded"
            >
              {t("cancelAnnotation")}
            </button>
            <button
              type="button"
              onClick={handleSaveAnnotation}
              disabled={!comment.trim()}
              className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded transition-colors"
            >
              <Check className="w-3 h-3" />
              {t("submitAnnotation")}
            </button>
          </div>
        </section>
      )}
    </section>
  );
};
