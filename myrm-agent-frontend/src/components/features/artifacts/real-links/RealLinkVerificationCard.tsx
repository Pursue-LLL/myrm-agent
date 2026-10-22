import React, { useState } from 'react';
import {
  Link2,
  ShieldCheck,
  AlertTriangle,
  ExternalLink,
  Sparkles,
  CheckCircle2,
  Code,
  Check,
  ChevronDown,
  ChevronUp,
  RefreshCw,
} from 'lucide-react';
import { useRealLinkAlignmentStore } from './useRealLinkAlignmentStore';

export const RealLinkVerificationCard: React.FC = () => {
  const {
    detectedLinks,
    alignmentRate,
    isApplied,
    codeSnippet,
    batchAlignPlaceholders,
    applyAlignedCode,
    resetState,
  } = useRealLinkAlignmentStore();

  const [showCode, setShowCode] = useState(false);
  const [copiedCode, setCopiedCode] = useState(false);

  const placeholderCount = detectedLinks.filter(
    (l) => l.status === 'placeholder_detected'
  ).length;

  const handleCopyCode = async () => {
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard) {
        await navigator.clipboard.writeText(codeSnippet);
      }
      setCopiedCode(true);
      setTimeout(() => {
        setCopiedCode(false);
      }, 2000);
    } catch {
      // 容错处理
    }
  };

  return (
    <div className="w-full max-w-4xl mx-auto rounded-2xl border border-slate-800 bg-slate-900/95 p-6 text-slate-100 shadow-2xl backdrop-blur-xl">
      {/* 头部元信息与健康度评分 */}
      <div className="flex flex-col gap-4 border-b border-slate-800 pb-5 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
            <Link2 className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-white tracking-tight">
                真实官方外部链接对齐与实战商用检验
              </h2>
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold border ${
                  alignmentRate === 100
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                    : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                }`}
              >
                {alignmentRate === 100 ? (
                  <ShieldCheck className="h-3 w-3" />
                ) : (
                  <AlertTriangle className="h-3 w-3" />
                )}
                <span>商用对齐率: {alignmentRate}%</span>
              </span>
            </div>
            <p className="mt-0.5 text-xs text-slate-400">
              杜绝 href=&quot;#&quot; 假数据玩具 • 自动对齐权威官方有效二级链接
            </p>
          </div>
        </div>

        {/* 顶部操作区 */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={resetState}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700 transition-colors"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>重置</span>
          </button>

          {placeholderCount > 0 && (
            <button
              type="button"
              onClick={batchAlignPlaceholders}
              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-md hover:bg-indigo-500 active:scale-95 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <Sparkles className="h-3.5 w-3.5" />
              <span>一键批量对齐官方实体 ({placeholderCount})</span>
            </button>
          )}

          <button
            type="button"
            onClick={applyAlignedCode}
            disabled={isApplied}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all ${
              isApplied
                ? 'bg-emerald-600/20 text-emerald-300 border border-emerald-500/30'
                : 'bg-emerald-600 text-white shadow-md hover:bg-emerald-500 active:scale-95'
            }`}
          >
            {isApplied ? (
              <>
                <Check className="h-3.5 w-3.5 text-emerald-400" />
                <span>代码已安全生效</span>
              </>
            ) : (
              <>
                <CheckCircle2 className="h-3.5 w-3.5" />
                <span>应用并替换到源码</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* 提示通知条 */}
      {placeholderCount > 0 ? (
        <div
          data-testid="placeholder-alert-banner"
          className="my-4 flex items-center justify-between rounded-lg border border-amber-500/30 bg-amber-950/40 p-3 text-xs text-amber-200"
        >
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0" />
            <span>
              检测到 <strong>{placeholderCount}</strong> 处未商用占位假链
              (href=&apos;#&apos; 或 example.com)，点击上方按钮可一键对齐企业官方二级服务。
            </span>
          </div>
        </div>
      ) : (
        <div
          data-testid="aligned-success-banner"
          className="my-4 flex items-center justify-between rounded-lg border border-emerald-500/30 bg-emerald-950/40 p-3 text-xs text-emerald-200"
        >
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-emerald-400 shrink-0" />
            <span>
              全量外链 100% 真实对齐！页面已具备开箱即用的工业级商用交付能力。
            </span>
          </div>
        </div>
      )}

      {/* 扫描到的链接实体清单 */}
      <div className="mt-4 space-y-2.5">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          已识别的超链接与实体对齐清单 ({detectedLinks.length})
        </h3>

        <div className="space-y-2">
          {detectedLinks.map((item) => {
            const isAligned = item.status === 'aligned';

            return (
              <div
                key={item.id}
                className="flex flex-col gap-2 rounded-xl border border-slate-800 bg-slate-850/60 p-3.5 text-xs transition-all hover:border-slate-700 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-white">
                      &quot;{item.anchorText}&quot;
                    </span>
                    <span
                      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium border ${
                        isAligned
                          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                          : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                      }`}
                    >
                      {isAligned ? '已对齐官方真实实体' : '占位假链需对齐'}
                    </span>
                    <span className="text-[10px] text-slate-400">
                      分类: {item.category}
                    </span>
                  </div>

                  <div className="mt-1 flex flex-col gap-1 sm:flex-row sm:items-center text-[11px]">
                    <span className="text-slate-400">原链接:</span>
                    <code className="rounded bg-slate-800 px-1 py-0.5 font-mono text-rose-300">
                      {item.originalHref}
                    </code>
                    {item.resolvedRealUrl && (
                      <>
                        <span className="text-slate-500">→</span>
                        <span className="text-slate-400">真实对齐实体:</span>
                        <a
                          href={item.resolvedRealUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 font-mono text-emerald-400 hover:underline"
                        >
                          <span>{item.targetEntityName ?? item.resolvedRealUrl}</span>
                          <ExternalLink className="h-2.5 w-2.5" />
                        </a>
                      </>
                    )}
                  </div>
                </div>

                <div className="text-[10px] text-slate-400 shrink-0">
                  {item.reason}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 底部代码展示抽屉 */}
      <div className="mt-5 border-t border-slate-800 pt-4">
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={() => {
              setShowCode(!showCode);
            }}
            className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-400 hover:text-indigo-300"
          >
            <Code className="h-3.5 w-3.5" />
            <span>{showCode ? '收起网页源码' : '查看对齐后的商用网页代码'}</span>
            {showCode ? (
              <ChevronUp className="h-3 w-3" />
            ) : (
              <ChevronDown className="h-3 w-3" />
            )}
          </button>

          {showCode && (
            <button
              type="button"
              onClick={handleCopyCode}
              className="inline-flex items-center gap-1 rounded bg-slate-800 px-2.5 py-1 text-[11px] text-slate-300 hover:bg-slate-700 transition-colors"
            >
              {copiedCode ? (
                <Check className="h-3 w-3 text-emerald-400" />
              ) : (
                <Code className="h-3 w-3" />
              )}
              <span>{copiedCode ? '已复制' : '复制商用代码'}</span>
            </button>
          )}
        </div>

        {showCode && (
          <div className="mt-3 rounded-xl border border-slate-800 bg-slate-950 p-3.5 font-mono text-xs text-slate-300">
            <pre className="max-h-60 overflow-y-auto whitespace-pre-wrap leading-relaxed text-indigo-200/90 scrollbar-thin">
              {codeSnippet}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
};
