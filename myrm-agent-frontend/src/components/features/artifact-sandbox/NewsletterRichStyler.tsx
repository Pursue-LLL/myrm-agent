/**
 * NewsletterRichStyler.tsx
 * 多主题自适应富文本排版器与微信公众号/邮件内联样式一键复制面板
 */

import React, { useMemo, useState } from 'react';
import {
  Check,
  Copy,
  Download,
  FileCode,
  Palette,
  Sparkles,
} from 'lucide-react';
import type { NewsletterTheme, RichCopyResult } from './artifactSandboxTypes';
import {
  THEME_DEFINITIONS,
  bundleSingleFileOfflineHtml,
  compileInlinedHtml,
} from './artifactSandboxEngine';
import { useArtifactSandboxStore } from './useArtifactSandboxStore';

export interface NewsletterRichStylerProps {
  className?: string;
  onCopySuccess?: (result: RichCopyResult) => void;
  onExportOffline?: (htmlString: string) => void;
}

const themeList: NewsletterTheme[] = [
  'mint_breeze',
  'executive_noir',
  'cyber_blue',
  'retro_amber',
];

export const NewsletterRichStyler: React.FC<NewsletterRichStylerProps> = ({
  className = '',
  onCopySuccess,
  onExportOffline,
}) => {
  const activeArtifact = useArtifactSandboxStore((state) => state.activeArtifact);
  const activeTheme = useArtifactSandboxStore((state) => state.activeTheme);
  const setActiveTheme = useArtifactSandboxStore(
    (state) => state.setActiveTheme
  );
  const setLastCopyResult = useArtifactSandboxStore(
    (state) => state.setLastCopyResult
  );

  const [copied, setCopied] = useState(false);

  const inlinedHtml = useMemo(() => {
    const raw =
      activeArtifact?.rawContent ?? '<h1>空排版工件</h1><p>无内容文本</p>';
    return compileInlinedHtml(raw, activeTheme);
  }, [activeArtifact, activeTheme]);

  const handleCopyRichHtml = async (): Promise<void> => {
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard !== undefined) {
        if (typeof ClipboardItem !== 'undefined') {
          const blobHtml = new Blob([inlinedHtml], { type: 'text/html' });
          const blobPlain = new Blob([inlinedHtml], { type: 'text/plain' });
          await navigator.clipboard.write([
            new ClipboardItem({
              'text/html': blobHtml,
              'text/plain': blobPlain,
            }),
          ]);
        } else {
          await navigator.clipboard.writeText(inlinedHtml);
        }
      }

      const result: RichCopyResult = {
        success: true,
        copiedChars: inlinedHtml.length,
        themeUsed: activeTheme,
        timestamp: Date.now(),
      };
      setLastCopyResult(result);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);

      if (onCopySuccess !== undefined) {
        onCopySuccess(result);
      }
    } catch {
      const failResult: RichCopyResult = {
        success: false,
        copiedChars: 0,
        themeUsed: activeTheme,
        error: '剪贴板写入受限',
        timestamp: Date.now(),
      };
      setLastCopyResult(failResult);
    }
  };

  const handleExportOfflineHtml = (): void => {
    const bundled = bundleSingleFileOfflineHtml(
      inlinedHtml,
      activeArtifact?.assets ?? []
    );
    if (onExportOffline !== undefined) {
      onExportOffline(bundled);
    }
  };

  return (
    <section
      data-testid="newsletter-rich-styler"
      aria-label="多主题自适应富文本排版器"
      className={`flex flex-col bg-slate-900 border border-slate-700/80 rounded-2xl shadow-xl overflow-hidden p-4 gap-4 ${className}`}
    >
      {/* 头部主题选择条 */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <Palette className="w-5 h-5 text-blue-400" />
          <h2 className="text-sm font-semibold text-slate-200">
            富媒体多主题排版引擎
          </h2>
        </div>

        {/* 动作区 */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            data-testid="export-offline-html-btn"
            onClick={handleExportOfflineHtml}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 text-slate-300 hover:bg-slate-700 border border-slate-700 transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            <span>导出单文件 HTML</span>
          </button>

          <button
            type="button"
            data-testid="copy-rich-html-btn"
            onClick={handleCopyRichHtml}
            className={`flex items-center gap-1 px-3.5 py-1.5 rounded-lg text-xs font-semibold shadow transition-colors ${
              copied
                ? 'bg-emerald-600 text-white'
                : 'bg-blue-600 text-white hover:bg-blue-500'
            }`}
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5" />
                <span>已复制公众号富文本!</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                <span>一键复制到公众号 / 邮件</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* 主题预设选项网格 */}
      <div className="grid grid-cols-4 gap-2.5">
        {themeList.map((themeKey) => {
          const def = THEME_DEFINITIONS[themeKey];
          const isSelected = activeTheme === themeKey;
          return (
            <button
              key={themeKey}
              type="button"
              data-testid={`theme-card-${themeKey}`}
              onClick={() => setActiveTheme(themeKey)}
              className={`flex flex-col text-left p-2.5 rounded-xl border transition-all ${
                isSelected
                  ? 'bg-slate-800/90 border-blue-500 ring-2 ring-blue-500/30 shadow-md'
                  : 'bg-slate-950/60 border-slate-800 hover:border-slate-700'
              }`}
            >
              <div className="flex items-center justify-between w-full">
                <span className="text-xs font-bold text-slate-200">
                  {def.name}
                </span>
                <span
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: def.accentColor }}
                />
              </div>
              <span className="text-[10px] text-slate-400 mt-1 line-clamp-2 leading-relaxed">
                {def.description}
              </span>
            </button>
          );
        })}
      </div>

      {/* 实时内联 HTML 预览面板 */}
      <div className="flex flex-col gap-1.5 flex-1 min-h-[300px]">
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span className="flex items-center gap-1 font-medium">
            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
            <span>实时富文本内联排版预览:</span>
          </span>
          <span className="text-[11px] font-mono text-slate-500">
            全 CSS 已内联编译为 style 属性
          </span>
        </div>

        <div
          data-testid="rich-html-preview-container"
          className="flex-1 bg-slate-950/80 rounded-xl border border-slate-800 p-4 overflow-auto max-h-[400px]"
        >
          {/* 安全富文本渲染沙盒容器 */}
          <div
            data-testid="rich-html-rendered-body"
            dangerouslySetInnerHTML={{ __html: inlinedHtml }}
          />
        </div>
      </div>

      {/* 底部格式小提示 */}
      <div className="flex items-center gap-1.5 text-[11px] text-slate-400 border-t border-slate-800 pt-2">
        <FileCode className="w-3.5 h-3.5 text-blue-400" />
        <span>支持直接在微信公众号、知乎专栏、Outlook 及各类富文本邮件客户端中直接 Ctrl+V 粘贴。</span>
      </div>
    </section>
  );
};
