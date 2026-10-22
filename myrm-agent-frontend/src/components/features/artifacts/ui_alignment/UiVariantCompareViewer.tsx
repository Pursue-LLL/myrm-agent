/**
 * [INPUT]
 * - chatId: string
 * - isOpen?: boolean
 * - onClose?: () => void
 *
 * [OUTPUT]
 * - UiVariantCompareViewer: Interactive side-by-side design variant compare & visual alignment viewer
 *
 * [POS]
 * Visual alignment compare viewer for Multi-Turn UI Design Visual Alignment Workflow (Item 39 P0).
 * Strictly under 320 lines. Zero `any`.
 */

import React, { useEffect, useState } from "react";
import {
  Layout,
  CheckCircle2,
  PenTool,
  Sparkles,
  FileCheck,
  X,
  Layers,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { VisualAnnotationOverlay } from "./VisualAnnotationOverlay";
import { useUiAlignmentStore } from "./useUiAlignmentStore";

interface UiVariantCompareViewerProps {
  chatId: string;
  isOpen?: boolean;
  onClose?: () => void;
}

export const UiVariantCompareViewer: React.FC<UiVariantCompareViewerProps> = ({
  chatId,
  isOpen = true,
  onClose,
}) => {
  const t = useTranslations("uiAlignment");

  const {
    variants,
    selectedVariantId,
    annotations,
    activeContract,
    isAnnotating,
    isLoading,
    selectVariant,
    setAnnotating,
    fetchVariants,
    fetchAnnotations,
    finalizeContract,
    fetchContract,
  } = useUiAlignmentStore();

  const [showPromptDetails, setShowPromptDetails] = useState(false);

  useEffect(() => {
    if (chatId) {
      void fetchVariants(chatId);
      void fetchContract(chatId);
    }
  }, [chatId, fetchVariants, fetchContract]);

  useEffect(() => {
    if (chatId && selectedVariantId) {
      void fetchAnnotations(chatId, selectedVariantId);
    }
  }, [chatId, selectedVariantId, fetchAnnotations]);

  if (!isOpen) {
    return null;
  }

  const selectedVariant = variants.find((v) => v.variant_id === selectedVariantId) ?? variants[0];
  const currentAnnotations = selectedVariant ? annotations[selectedVariant.variant_id] ?? [] : [];

  const handleFinalize = async () => {
    if (selectedVariant) {
      await finalizeContract(chatId, selectedVariant.variant_id);
    }
  };

  return (
    <dialog
      open
      aria-label={t("title")}
      className="fixed inset-0 z-50 flex items-center justify-center w-full h-full p-4 bg-black/70 backdrop-blur-sm"
    >
      <div className="relative flex flex-col w-full max-w-5xl h-[85vh] bg-zinc-950 border border-zinc-800 rounded-xl shadow-2xl overflow-hidden text-zinc-100">
        {/* Header Bar */}
        <header className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 bg-zinc-900/60">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400">
              <Layout className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold leading-none">{t("title")}</h2>
              <p className="mt-1 text-xs text-zinc-400">{t("subtitle")}</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {activeContract && (
              <div className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded-full">
                <FileCheck className="w-3.5 h-3.5" />
                <span>{t("contractFinalizedBadge")}</span>
              </div>
            )}

            <button
              type="button"
              onClick={() => setAnnotating(!isAnnotating)}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition-all ${
                isAnnotating
                  ? "bg-amber-500/20 border-amber-500 text-amber-300"
                  : "bg-zinc-800/80 border-zinc-700 hover:bg-zinc-800 text-zinc-300"
              }`}
            >
              <PenTool className="w-3.5 h-3.5" />
              <span>{isAnnotating ? t("exitAnnotate") : t("annotateMode")}</span>
            </button>

            <button
              type="button"
              onClick={handleFinalize}
              disabled={!selectedVariant || isLoading}
              className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg shadow-sm transition-all"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>{t("finalizeContract")}</span>
            </button>

            {onClose && (
              <button
                type="button"
                onClick={onClose}
                aria-label={t("close")}
                className="p-1.5 text-zinc-400 hover:text-zinc-100 rounded-lg hover:bg-zinc-800 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </header>

        {/* Content Area */}
        <div className="flex flex-1 overflow-hidden">
          {/* Variant Selector Sidebar */}
          <aside className="w-72 border-r border-zinc-800 p-4 overflow-y-auto space-y-3 bg-zinc-900/30">
            <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5" />
              <span>Variants ({variants.length})</span>
            </h3>

            {variants.length === 0 ? (
              <div className="p-4 text-center text-xs text-zinc-500 border border-dashed border-zinc-800 rounded-lg">
                {t("noVariants")}
              </div>
            ) : (
              variants.map((v) => {
                const isSelected = selectedVariant?.variant_id === v.variant_id;
                const noteCount = (annotations[v.variant_id] ?? []).length;
                return (
                  <button
                    key={v.variant_id}
                    type="button"
                    onClick={() => selectVariant(v.variant_id)}
                    className={`w-full text-left p-3 rounded-lg border transition-all ${
                      isSelected
                        ? "border-indigo-500 bg-indigo-950/20 shadow-md ring-1 ring-indigo-500/50"
                        : "border-zinc-800 hover:border-zinc-700 bg-zinc-900/40"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-xs font-semibold text-zinc-200 truncate">{v.title}</span>
                      {isSelected && <CheckCircle2 className="w-3.5 h-3.5 text-indigo-400 flex-shrink-0" />}
                    </div>
                    <div className="flex items-center gap-2 text-[11px] text-zinc-400">
                      <span className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 font-mono text-[10px]">
                        {v.style_theme}
                      </span>
                      <span>
                        {noteCount} {t("annotationsCount")}
                      </span>
                    </div>
                  </button>
                );
              })
            )}
          </aside>

          {/* Main Canvas & Contract Area */}
          <main className="flex-1 flex flex-col overflow-hidden bg-zinc-950 p-6 space-y-4">
            {selectedVariant ? (
              <>
                {/* Meta details & Tokens */}
                <div className="flex items-center justify-between p-3 rounded-lg bg-zinc-900/50 border border-zinc-800">
                  <div>
                    <h4 className="text-sm font-medium text-zinc-100">{selectedVariant.title}</h4>
                    <p className="text-xs text-zinc-400">{selectedVariant.description || t("selectedVariant")}</p>
                  </div>
                  {/* Token Palette Preview */}
                  <div className="flex items-center gap-1.5">
                    {Object.entries(selectedVariant.css_tokens).map(([k, val]) => (
                      <span
                        key={k}
                        title={`${k}: ${val}`}
                        className="px-2 py-0.5 text-[10px] rounded bg-zinc-800 border border-zinc-700 text-zinc-300 font-mono"
                      >
                        {k}: {val}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Live Preview Canvas Container with Overlay */}
                <div className="relative flex-1 border border-zinc-800 rounded-lg overflow-hidden bg-zinc-900/20">
                  {/* Mock Render Frame */}
                  <div
                    className="w-full h-full p-4 overflow-auto font-sans"
                    dangerouslySetInnerHTML={{ __html: selectedVariant.html_content }}
                  />

                  {/* Interactive Visual Annotation Overlay */}
                  <VisualAnnotationOverlay
                    variantId={selectedVariant.variant_id}
                    chatId={chatId}
                    annotations={currentAnnotations}
                    isAnnotating={isAnnotating}
                  />
                </div>

                {/* Finalized Contract Accordion (if exists) */}
                {activeContract && (
                  <div className="border border-emerald-500/30 bg-emerald-950/10 rounded-lg p-3">
                    <button
                      type="button"
                      onClick={() => setShowPromptDetails(!showPromptDetails)}
                      className="flex items-center justify-between w-full text-xs font-medium text-emerald-300"
                    >
                      <span className="flex items-center gap-1.5">
                        <FileCheck className="w-4 h-4 text-emerald-400" />
                        <span>
                          {t("contractFinalizedBadge")} (ID: {activeContract.contract_id})
                        </span>
                      </span>
                      {showPromptDetails ? (
                        <ChevronUp className="w-3.5 h-3.5" />
                      ) : (
                        <ChevronDown className="w-3.5 h-3.5" />
                      )}
                    </button>
                    {showPromptDetails && (
                      <pre className="mt-2.5 p-3 rounded bg-zinc-950 border border-zinc-800 text-[11px] font-mono text-zinc-300 overflow-x-auto whitespace-pre-wrap max-h-36">
                        {activeContract.enforcement_prompt}
                      </pre>
                    )}
                  </div>
                )}
              </>
            ) : (
              <div className="flex flex-col items-center justify-center flex-1 text-zinc-500 text-xs">
                <Layout className="w-8 h-8 mb-2 opacity-50" />
                <p>{t("noVariants")}</p>
              </div>
            )}
          </main>
        </div>
      </div>
    </dialog>
  );
};
