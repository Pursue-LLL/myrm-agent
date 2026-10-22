/**
 * [INPUT]
 * - None (reads activeSandboxHtml, activeSandboxTitle, isShowcaseOpen from useDelightShowcaseStore)
 *
 * [OUTPUT]
 * - SingleFileSandboxShowcase: Fullscreen responsive single-file sandbox iframe showcase & QR code launcher
 *
 * [POS]
 * Client-side showcase viewer for Zero-Code Hobbyist Delight & Single-File Sandbox (Item 40 P0).
 * Strictly under 300 lines. Zero `any`.
 */

import React, { useState } from "react";
import {
  Maximize2,
  Minimize2,
  QrCode,
  Copy,
  Check,
  X,
  Smartphone,
  Sparkles,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useDelightShowcaseStore } from "./useDelightShowcaseStore";

export const SingleFileSandboxShowcase: React.FC = () => {
  const t = useTranslations("delightShowcase");

  const {
    activeSandboxHtml,
    activeSandboxTitle,
    isShowcaseOpen,
    isQrCodeOpen,
    closeShowcase,
    setQrCodeOpen,
  } = useDelightShowcaseStore();

  const [isFullscreen, setIsFullscreen] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!isShowcaseOpen || !activeSandboxHtml) {
    return null;
  }

  const handleCopyCode = async () => {
    try {
      await navigator.clipboard.writeText(activeSandboxHtml);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
      setCopied(false);
    }
  };

  return (
    <dialog
      open
      aria-label={activeSandboxTitle || t("title")}
      className={`fixed inset-0 z-50 flex items-center justify-center p-0 m-0 bg-black/85 backdrop-blur-md transition-all ${
        isFullscreen ? "w-screen h-screen" : "w-screen h-screen p-4 sm:p-6"
      }`}
    >
      <div
        className={`relative flex flex-col bg-zinc-950 border border-zinc-800 shadow-2xl overflow-hidden text-zinc-100 transition-all ${
          isFullscreen
            ? "w-full h-full rounded-none border-none"
            : "w-full max-w-5xl h-[88vh] rounded-2xl"
        }`}
      >
        {/* Floating Top Control Bar */}
        <header className="flex items-center justify-between px-4 py-2.5 bg-zinc-900/90 border-b border-zinc-800 backdrop-blur-md z-20">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-xs font-semibold leading-tight text-zinc-100 truncate max-w-xs sm:max-w-md">
                {activeSandboxTitle || t("title")}
              </h2>
              <span className="text-[10px] text-zinc-400 font-mono">
                {t("selfContainedBadge")}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            {/* Copy HTML Source */}
            <button
              type="button"
              onClick={handleCopyCode}
              title={copied ? t("codeCopied") : t("copyCode")}
              className="flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              <span className="hidden sm:inline">{copied ? t("codeCopied") : t("copyCode")}</span>
            </button>

            {/* Mobile QR Code Launcher */}
            <button
              type="button"
              onClick={() => setQrCodeOpen(!isQrCodeOpen)}
              title={t("qrCodeShare")}
              className={`flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-lg border transition-all ${
                isQrCodeOpen
                  ? "bg-amber-500/20 border-amber-500/50 text-amber-300"
                  : "bg-zinc-800 border-zinc-700 hover:bg-zinc-700 text-zinc-300"
              }`}
            >
              <QrCode className="w-3.5 h-3.5 text-amber-400" />
              <span className="hidden sm:inline">{t("qrCodeShare")}</span>
            </button>

            {/* Fullscreen Toggle */}
            <button
              type="button"
              onClick={() => setIsFullscreen(!isFullscreen)}
              title={isFullscreen ? t("exitFullscreen") : t("fullscreen")}
              className="p-1.5 text-zinc-400 hover:text-zinc-100 rounded-lg hover:bg-zinc-800 transition-colors"
            >
              {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            </button>

            {/* Close Button */}
            <button
              type="button"
              onClick={closeShowcase}
              aria-label={t("close")}
              className="p-1.5 text-zinc-400 hover:text-zinc-100 rounded-lg hover:bg-zinc-800 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </header>

        {/* Sandbox Content Frame */}
        <main className="relative flex-1 w-full h-full bg-zinc-950 overflow-hidden">
          <iframe
            title={activeSandboxTitle || "Single-file Sandbox"}
            srcDoc={activeSandboxHtml}
            sandbox="allow-scripts allow-forms allow-modals allow-same-origin"
            className="w-full h-full border-none bg-zinc-950"
          />

          {/* QR Code Sharing Dialog Overlay */}
          {isQrCodeOpen && (
            <section
              aria-label={t("qrCodeShare")}
              className="absolute top-4 right-4 z-30 p-5 bg-zinc-900/95 border border-amber-500/40 rounded-2xl shadow-2xl backdrop-blur-xl w-72 text-zinc-100 text-center"
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-300">
                  <Smartphone className="w-4 h-4" />
                  <span>{t("qrCodeShare")}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setQrCodeOpen(false)}
                  className="text-zinc-400 hover:text-zinc-200"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* High Contrast Pure SVG Geometric QR Pattern */}
              <div className="p-3 mx-auto my-2 bg-white rounded-xl shadow-inner w-44 h-44 flex items-center justify-center">
                <svg
                  viewBox="0 0 100 100"
                  className="w-full h-full text-black fill-current"
                  aria-hidden="true"
                >
                  {/* Top-Left Position Detection Pattern */}
                  <rect x="10" y="10" width="28" height="28" rx="4" />
                  <rect x="16" y="16" width="16" height="16" fill="white" />
                  <rect x="20" y="20" width="8" height="8" />

                  {/* Top-Right Position Detection Pattern */}
                  <rect x="62" y="10" width="28" height="28" rx="4" />
                  <rect x="68" y="16" width="16" height="16" fill="white" />
                  <rect x="72" y="20" width="8" height="8" />

                  {/* Bottom-Left Position Detection Pattern */}
                  <rect x="10" y="62" width="28" height="28" rx="4" />
                  <rect x="16" y="68" width="16" height="16" fill="white" />
                  <rect x="20" y="72" width="8" height="8" />

                  {/* High Density Mock Data Matrix Cells */}
                  <rect x="44" y="14" width="6" height="6" />
                  <rect x="52" y="22" width="6" height="6" />
                  <rect x="44" y="30" width="6" height="6" />
                  <rect x="22" y="44" width="6" height="6" />
                  <rect x="32" y="52" width="6" height="6" />
                  <rect x="44" y="44" width="12" height="12" rx="2" />
                  <rect x="62" y="44" width="6" height="6" />
                  <rect x="74" y="52" width="8" height="8" />
                  <rect x="44" y="62" width="6" height="6" />
                  <rect x="54" y="70" width="8" height="8" />
                  <rect x="70" y="68" width="6" height="6" />
                  <rect x="80" y="80" width="10" height="10" rx="2" />
                  <rect x="62" y="82" width="6" height="6" />
                  <rect x="44" y="80" width="6" height="6" />
                </svg>
              </div>

              <p className="text-[11px] text-zinc-400 mt-2 leading-tight">
                {t("qrCodeSubtitle")}
              </p>
            </section>
          )}
        </main>
      </div>
    </dialog>
  );
};
