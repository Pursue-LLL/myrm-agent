/**
 * [INPUT]
 * - chatId: string
 * - isOpen?: boolean
 * - onClose?: () => void
 *
 * [OUTPUT]
 * - WidgetGeneratorModal: Visual dialog for configuring embed widget options and copying single-line snippet
 *
 * [POS]
 * Code generator modal for Embeddable Agent Widget (Item 41 P1).
 * Strictly under 280 lines. Zero `any`.
 */

import React, { useEffect, useState } from "react";
import {
  Code,
  Copy,
  Check,
  X,
  Layers,
  Globe,
  Sliders,
  Shield,
  Palette,
  ExternalLink,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useWidgetBridgeStore } from "./useWidgetBridgeStore";
import type { WidgetDisplayMode, WidgetTheme } from "./widgetTypes";

interface WidgetGeneratorModalProps {
  chatId: string;
  isOpen?: boolean;
  onClose?: () => void;
}

export const WidgetGeneratorModal: React.FC<WidgetGeneratorModalProps> = ({
  chatId,
  isOpen = true,
  onClose,
}) => {
  const t = useTranslations("embedWidget");
  const {
    generatedSnippet,
    isLoading,
    generateSnippet,
    setGeneratorModalOpen,
  } = useWidgetBridgeStore();

  const [mode, setMode] = useState<WidgetDisplayMode>("floating_bubble");
  const [theme, setTheme] = useState<WidgetTheme>("light");
  const [allowedOrigin, setAllowedOrigin] = useState("*");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const origin = typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";
    void generateSnippet(chatId, {
      mode,
      theme,
      allowedOrigin,
      baseUrl: origin,
    });
  }, [chatId, mode, theme, allowedOrigin, generateSnippet]);

  const handleCopy = async () => {
    if (!generatedSnippet) {
      return;
    }
    try {
      await navigator.clipboard.writeText(generatedSnippet);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  };

  const handleClose = () => {
    setGeneratorModalOpen(false);
    if (onClose) {
      onClose();
    }
  };

  if (!isOpen) {
    return null;
  }

  return (
    <dialog
      open
      aria-labelledby="widget-generator-title"
      className="fixed inset-0 z-50 flex h-full w-full items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
    >
      <div className="relative flex w-full max-w-2xl flex-col rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900">
        {/* Header */}
        <header className="flex items-center justify-between border-b border-slate-200 px-6 py-4 dark:border-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-50 text-blue-600 dark:bg-blue-950/60 dark:text-blue-400">
              <Code className="h-5 w-5" />
            </div>
            <div>
              <h2
                id="widget-generator-title"
                className="text-base font-semibold text-slate-900 dark:text-slate-100"
              >
                {t("generatorTitle")}
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {t("generatorSubtitle")}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            aria-label={t("close")}
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        {/* Configuration Controls */}
        <div className="flex flex-col gap-5 p-6">
          {/* Display Mode Selection */}
          <div>
            <label className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-300">
              <Layers className="h-3.5 w-3.5 text-blue-500" />
              {t("displayMode")}
            </label>
            <div className="grid grid-cols-3 gap-3">
              {(
                [
                  { id: "floating_bubble", label: t("modeBubble"), desc: t("modeBubbleDesc") },
                  { id: "slideout_drawer", label: t("modeDrawer"), desc: t("modeDrawerDesc") },
                  { id: "inline_container", label: t("modeInline"), desc: t("modeInlineDesc") },
                ] as const
              ).map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setMode(item.id)}
                  className={`flex flex-col rounded-xl border p-3 text-left transition-all ${
                    mode === item.id
                      ? "border-blue-600 bg-blue-50/50 shadow-sm dark:border-blue-500 dark:bg-blue-950/30"
                      : "border-slate-200 hover:border-slate-300 dark:border-slate-800 dark:hover:border-slate-700"
                  }`}
                >
                  <span
                    className={`text-xs font-semibold ${
                      mode === item.id
                        ? "text-blue-700 dark:text-blue-400"
                        : "text-slate-700 dark:text-slate-300"
                    }`}
                  >
                    {item.label}
                  </span>
                  <span className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                    {item.desc}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Theme & Allowed Origin Controls */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-300">
                <Palette className="h-3.5 w-3.5 text-blue-500" />
                {t("themeLabel")}
              </label>
              <select
                value={theme}
                onChange={(e) => setTheme(e.target.value as WidgetTheme)}
                className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-800 outline-none focus:border-blue-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200"
              >
                <option value="light">{t("themeLight")}</option>
                <option value="dark">{t("themeDark")}</option>
                <option value="auto">{t("themeAuto")}</option>
              </select>
            </div>

            <div>
              <label className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-300">
                <Shield className="h-3.5 w-3.5 text-blue-500" />
                {t("allowedOriginLabel")}
              </label>
              <input
                type="text"
                value={allowedOrigin}
                onChange={(e) => setAllowedOrigin(e.target.value)}
                placeholder="https://example.com or *"
                className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-800 outline-none focus:border-blue-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200"
              />
            </div>
          </div>

          {/* Generated Code Snippet */}
          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-300">
                <Code className="h-3.5 w-3.5 text-blue-500" />
                {t("embedSnippet")}
              </label>
              <span className="text-[11px] text-slate-500 dark:text-slate-400">
                {t("snippetInstructions")}
              </span>
            </div>

            <div className="relative rounded-xl border border-slate-800 bg-slate-950 p-3.5 font-mono text-xs text-slate-200 shadow-inner">
              <pre className="max-h-36 overflow-x-auto whitespace-pre-wrap break-all pr-12 text-[11px] leading-relaxed">
                {generatedSnippet}
              </pre>
              <button
                type="button"
                onClick={handleCopy}
                disabled={isLoading}
                className="absolute right-3 top-3 flex items-center gap-1 rounded-lg bg-blue-600 px-2.5 py-1.5 text-xs font-medium text-white shadow transition-all hover:bg-blue-500"
                aria-label={copied ? t("copied") : t("copySnippet")}
              >
                {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                <span>{copied ? t("copied") : t("copySnippet")}</span>
              </button>
            </div>
          </div>
        </div>

        {/* Footer */}
        <footer className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-6 py-3.5 dark:border-slate-800 dark:bg-slate-950/60">
          <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
            <Globe className="h-3.5 w-3.5 text-emerald-500" />
            <span>{t("ipcBridgeEnabled")}</span>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="rounded-lg bg-slate-200 px-4 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-300 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
          >
            {t("done")}
          </button>
        </footer>
      </div>
    </dialog>
  );
};
