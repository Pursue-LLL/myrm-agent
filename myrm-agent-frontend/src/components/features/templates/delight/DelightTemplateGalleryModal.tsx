/**
 * [INPUT]
 * - onApplyPrompt?: (prompt: string) => void
 *
 * [OUTPUT]
 * - DelightTemplateGalleryModal: Fullscreen/modal gallery showcasing zero-code hobbyist templates
 *
 * [POS]
 * Client-side gallery modal for Zero-Code Hobbyist Delight Inspiration (Item 40 P0).
 * Strictly under 320 lines. Zero `any`.
 */

import React, { useEffect } from "react";
import {
  Sparkles,
  Cake,
  Gamepad2,
  Heart,
  Wrench,
  Palette,
  Search,
  Play,
  X,
  FileCode2,
} from "lucide-react";
import { useTranslations } from "next-intl";
import type { DelightCategory, DelightTemplateItem } from "./delightTypes";
import { useDelightShowcaseStore } from "./useDelightShowcaseStore";

interface DelightTemplateGalleryModalProps {
  onApplyPrompt?: (prompt: string) => void;
}

const CATEGORY_TABS: Array<{ id: DelightCategory; labelKey: string; icon: React.ElementType }> = [
  { id: "all", labelKey: "allCategories", icon: Sparkles },
  { id: "celebration", labelKey: "celebration", icon: Cake },
  { id: "interactive_fun", labelKey: "interactive_fun", icon: Gamepad2 },
  { id: "romance_memory", labelKey: "romance_memory", icon: Heart },
  { id: "utility_tools", labelKey: "utility_tools", icon: Wrench },
  { id: "generative_art", labelKey: "generative_art", icon: Palette },
];

export const DelightTemplateGalleryModal: React.FC<DelightTemplateGalleryModalProps> = ({
  onApplyPrompt,
}) => {
  const t = useTranslations("delightShowcase");

  const {
    templates,
    selectedCategory,
    searchQuery,
    isGalleryOpen,
    isLoading,
    setGalleryOpen,
    setSelectedCategory,
    setSearchQuery,
    fetchTemplates,
    openShowcaseWithHtml,
    fetchTemplateDetail,
  } = useDelightShowcaseStore();

  useEffect(() => {
    if (isGalleryOpen && templates.length === 0) {
      void fetchTemplates();
    }
  }, [isGalleryOpen, templates.length, fetchTemplates]);

  if (!isGalleryOpen) {
    return null;
  }

  const filtered = templates.filter((item) => {
    const matchCategory = selectedCategory === "all" || item.category === selectedCategory;
    const matchQuery =
      !searchQuery.trim() ||
      item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.tags.some((tag) => tag.toLowerCase().includes(searchQuery.toLowerCase()));
    return matchCategory && matchQuery;
  });

  const handlePreview = async (item: DelightTemplateItem) => {
    if (item.html_source) {
      openShowcaseWithHtml(item.title, item.html_source);
    } else {
      const detail = await fetchTemplateDetail(item.template_id);
      if (detail?.html_source) {
        openShowcaseWithHtml(detail.title, detail.html_source);
      }
    }
  };

  const handleUseTemplate = (item: DelightTemplateItem) => {
    if (onApplyPrompt) {
      onApplyPrompt(item.prompt_seed);
    }
    setGalleryOpen(false);
  };

  return (
    <dialog
      open
      aria-label={t("title")}
      className="fixed inset-0 z-50 flex items-center justify-center w-full h-full p-4 bg-black/75 backdrop-blur-sm"
    >
      <div className="relative flex flex-col w-full max-w-4xl h-[85vh] bg-zinc-950 border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden text-zinc-100">
        {/* Header Bar */}
        <header className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 bg-zinc-900/50">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-gradient-to-tr from-amber-500/20 to-rose-500/20 text-amber-400 border border-amber-500/30">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold leading-none">{t("title")}</h2>
              <p className="mt-1 text-xs text-zinc-400">{t("subtitle")}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setGalleryOpen(false)}
            aria-label={t("close")}
            className="p-1.5 text-zinc-400 hover:text-zinc-100 rounded-lg hover:bg-zinc-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        {/* Search & Tabs Toolbar */}
        <div className="p-4 border-b border-zinc-800/80 bg-zinc-900/20 space-y-3">
          {/* Search Box */}
          <div className="relative w-full">
            <Search className="absolute left-3 top-2.5 w-4 h-4 text-zinc-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t("searchPlaceholder")}
              className="w-full pl-9 pr-3 py-2 text-xs rounded-xl bg-zinc-900/80 border border-zinc-700/80 text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-amber-500 transition-colors"
            />
          </div>

          {/* Category Tabs */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 no-scrollbar">
            {CATEGORY_TABS.map((tab) => {
              const TabIcon = tab.icon;
              const isActive = selectedCategory === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setSelectedCategory(tab.id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg font-medium transition-all whitespace-nowrap ${
                    isActive
                      ? "bg-amber-500/20 border border-amber-500/50 text-amber-300 shadow-sm"
                      : "bg-zinc-900/60 border border-zinc-800 hover:border-zinc-700 text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  <TabIcon className="w-3.5 h-3.5" />
                  <span>{t(tab.labelKey)}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Gallery Grid Body */}
        <main className="flex-1 p-6 overflow-y-auto">
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-zinc-500 text-xs">
              <FileCode2 className="w-10 h-10 mb-2 opacity-40 text-amber-400" />
              <p>{t("noTemplatesFound")}</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filtered.map((item) => (
                <div
                  key={item.template_id}
                  className="flex flex-col justify-between p-4 rounded-xl border border-zinc-800/80 bg-zinc-900/40 hover:bg-zinc-900/70 hover:border-amber-500/40 transition-all shadow-sm group"
                >
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/10 border border-amber-500/20 text-amber-300">
                        {item.category}
                      </span>
                      <span className="text-[10px] text-zinc-500 font-mono">
                        {t("selfContainedBadge")}
                      </span>
                    </div>
                    <h3 className="text-sm font-semibold text-zinc-100 group-hover:text-amber-300 transition-colors line-clamp-1 mb-1.5">
                      {item.title}
                    </h3>
                    <p className="text-xs text-zinc-400 line-clamp-2 leading-relaxed mb-3">
                      {item.description}
                    </p>
                    <div className="flex flex-wrap gap-1 mb-4">
                      {item.tags.map((tag) => (
                        <span
                          key={tag}
                          className="px-1.5 py-0.5 rounded bg-zinc-800/80 text-[10px] text-zinc-400 font-mono"
                        >
                          #{tag}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 pt-3 border-t border-zinc-800/60">
                    <button
                      type="button"
                      onClick={() => void handlePreview(item)}
                      className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 transition-colors"
                    >
                      <Play className="w-3 h-3 text-amber-400" />
                      <span>{t("previewDemo")}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleUseTemplate(item)}
                      className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-amber-500 hover:bg-amber-400 text-zinc-950 font-semibold transition-colors"
                    >
                      <Sparkles className="w-3 h-3" />
                      <span>{t("useTemplate")}</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </main>
      </div>
    </dialog>
  );
};
