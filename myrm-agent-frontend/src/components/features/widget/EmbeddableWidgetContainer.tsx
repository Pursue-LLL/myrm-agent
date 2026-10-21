/**
 * [INPUT]
 * - children: React.ReactNode (the core ChatWindow or embedded agent view)
 * - chatId: string
 * - className?: string
 *
 * [OUTPUT]
 * - EmbeddableWidgetContainer: Multi-presentation container for embedded agent widget
 *
 * [POS]
 * Container component for Embeddable Agent Widget (Item 41 P1).
 * Supports floating bubble, slideout drawer, and inline embed layouts.
 * Strictly under 240 lines. Zero `any`.
 */

import React, { useEffect, useState } from "react";
import {
  MessageSquare,
  X,
  Minimize2,
  Maximize2,
  Layers,
  ShieldCheck,
  Globe,
  ExternalLink,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { HostContextBridge } from "./HostContextBridge";
import { useWidgetBridgeStore } from "./useWidgetBridgeStore";
import type { WidgetDisplayMode } from "./widgetTypes";

interface EmbeddableWidgetContainerProps {
  children: React.ReactNode;
  chatId: string;
  className?: string;
}

export const EmbeddableWidgetContainer: React.FC<EmbeddableWidgetContainerProps> = ({
  children,
  chatId,
  className = "",
}) => {
  const t = useTranslations("embedWidget");
  const {
    displayMode,
    isWidgetOpen,
    latestSnapshot,
    setWidgetOpen,
    setDisplayMode,
    fetchEmbedPolicy,
  } = useWidgetBridgeStore();

  const [isExpanded, setIsExpanded] = useState(false);

  useEffect(() => {
    void fetchEmbedPolicy(chatId);
    const teardown = HostContextBridge.initialize(chatId);
    return () => {
      teardown();
    };
  }, [chatId, fetchEmbedPolicy]);

  // Notify host of dimension updates when expanding/collapsing
  useEffect(() => {
    if (!isWidgetOpen) {
      HostContextBridge.notifyResize(64, 64);
    } else if (isExpanded) {
      HostContextBridge.notifyResize(800, 750);
    } else {
      HostContextBridge.notifyResize(420, 620);
    }
  }, [isWidgetOpen, isExpanded]);

  // Presentation 1: Inline Container (always expanded in host layout)
  if (displayMode === "inline_container") {
    return (
      <div
        className={`flex h-full w-full flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950 ${className}`}
      >
        {latestSnapshot && (
          <header className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
            <div className="flex items-center gap-1.5 truncate">
              <Globe className="h-3.5 w-3.5 shrink-0 text-blue-500" />
              <span className="truncate font-medium">{latestSnapshot.origin}</span>
              <span className="truncate opacity-75">({latestSnapshot.currentUrl})</span>
            </div>
            <div className="flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
              <ShieldCheck className="h-3 w-3" />
              <span>{t("contextSynced")}</span>
            </div>
          </header>
        )}
        <div className="flex-1 overflow-hidden">{children}</div>
      </div>
    );
  }

  // Presentation 2: Slideout Drawer
  if (displayMode === "slideout_drawer") {
    return (
      <>
        {!isWidgetOpen && (
          <button
            type="button"
            onClick={() => setWidgetOpen(true)}
            aria-label={t("openWidget")}
            className="fixed right-0 top-1/2 z-50 flex -translate-y-1/2 items-center gap-1.5 rounded-l-xl bg-blue-600 px-3 py-2.5 text-xs font-semibold text-white shadow-xl transition-all hover:bg-blue-700 hover:pr-4"
          >
            <MessageSquare className="h-4 w-4" />
            <span className="hidden sm:inline">{t("chatAssistant")}</span>
          </button>
        )}

        {isWidgetOpen && (
          <aside
            aria-label="Agent Slideout Drawer"
            className="fixed bottom-0 right-0 top-0 z-50 flex w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-2xl transition-transform dark:border-slate-800 dark:bg-slate-950"
          >
            <header className="flex h-12 items-center justify-between border-b border-slate-200 px-4 dark:border-slate-800">
              <div className="flex items-center gap-2">
                <Layers className="h-4 w-4 text-blue-500" />
                <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                  {t("drawerTitle")}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setWidgetOpen(false)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                aria-label={t("closeWidget")}
              >
                <X className="h-4 w-4" />
              </button>
            </header>
            <div className="flex-1 overflow-hidden">{children}</div>
          </aside>
        )}
      </>
    );
  }

  // Presentation 3: Floating Bubble (Default)
  return (
    <>
      {!isWidgetOpen && (
        <button
          type="button"
          onClick={() => setWidgetOpen(true)}
          aria-label={t("openWidget")}
          className="fixed bottom-5 right-5 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-blue-600 text-white shadow-2xl transition-transform hover:scale-105 hover:bg-blue-700 focus:outline-none focus:ring-4 focus:ring-blue-500/30"
        >
          <MessageSquare className="h-6 w-6" />
          {latestSnapshot && (
            <span className="absolute -right-0.5 -top-0.5 flex h-3.5 w-3.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-3.5 w-3.5 rounded-full bg-emerald-500" />
            </span>
          )}
        </button>
      )}

      {isWidgetOpen && (
        <section
          aria-label="Agent Floating Widget"
          className={`fixed bottom-5 right-5 z-50 flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl transition-all duration-200 dark:border-slate-800 dark:bg-slate-950 ${
            isExpanded ? "h-[750px] w-[800px]" : "h-[620px] w-[400px]"
          }`}
        >
          {/* Header Bar */}
          <header className="flex h-12 items-center justify-between border-b border-slate-200 bg-slate-50/80 px-3.5 backdrop-blur dark:border-slate-800 dark:bg-slate-900/80">
            <div className="flex items-center gap-2 truncate">
              <MessageSquare className="h-4 w-4 text-blue-500" />
              <span className="truncate text-sm font-semibold text-slate-800 dark:text-slate-100">
                {t("widgetTitle")}
              </span>
            </div>

            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setIsExpanded(!isExpanded)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-200/60 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                aria-label={isExpanded ? t("minimize") : t("maximize")}
              >
                {isExpanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
              </button>
              <button
                type="button"
                onClick={() => setWidgetOpen(false)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-200/60 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                aria-label={t("closeWidget")}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </header>

          {/* Connected Context Badge */}
          {latestSnapshot && (
            <div className="flex items-center justify-between border-b border-slate-100 bg-blue-50/50 px-3 py-1 text-[11px] text-blue-800 dark:border-slate-800 dark:bg-blue-950/30 dark:text-blue-300">
              <span className="truncate">
                {t("hostPage")}: {latestSnapshot.pageTitle || latestSnapshot.currentUrl}
              </span>
              <ShieldCheck className="h-3 w-3 shrink-0 text-emerald-500" />
            </div>
          )}

          {/* Agent View Body */}
          <div className="flex-1 overflow-hidden">{children}</div>
        </section>
      )}
    </>
  );
};
