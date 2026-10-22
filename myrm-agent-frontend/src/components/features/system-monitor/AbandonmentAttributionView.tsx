/**
 * [INPUT]
 * - abandonmentDistribution: Record<string, number> 常见弃用根因频次映射
 * - onDiagnose?: (path: string, content: string, has_llms_txt: boolean) => Promise<AeoPageDiagnosticData>
 * - diagnosticResult?: AeoPageDiagnosticData | null
 * - loading?: boolean
 *
 * [OUTPUT]
 * - AbandonmentAttributionView: 静默审判流失归因与页面 AEO 即时诊断透视组件
 *
 * [POS]
 * src/components/features/system-monitor/AbandonmentAttributionView.tsx — 静默审判流失归因与 AEO 诊断视图
 */

import React, { useState } from 'react';
import type { AeoPageDiagnosticData } from './agenticTrafficTypes';

export interface AbandonmentAttributionViewProps {
  abandonmentDistribution: Record<string, number>;
  onDiagnose?: (path: string, content: string, has_llms_txt: boolean) => Promise<AeoPageDiagnosticData>;
  diagnosticResult?: AeoPageDiagnosticData | null;
  loading?: boolean;
  className?: string;
}

const REASON_DESC_MAP: Record<string, { label: string; desc: string }> = {
  TOKEN_OVERFLOW_20K: { label: 'Token 撑爆截断 (>20k)', desc: '页面内容过长，撑爆 Agent 上下文' },
  LLMS_TXT_MISSING: { label: '缺少 llms.txt 规范', desc: '未提供 llms.txt，Agent 只能在复杂 HTML 盲爬' },
  FIRST_500_TOKENS_VAGUE: { label: '前 500 Token 缺乏核心示例', desc: '首屏缺乏可运行代码，400ms 内判定方案晦涩并放弃' },
  SPA_CLIENT_BLANK: { label: '纯 SPA 客户端空白页', desc: '无头 HTTP Agent 无法执行 JS，抓取到空白内容' },
  API_SPEC_UNRESOLVABLE: { label: 'API 规范解析受阻', desc: 'OpenAPI/Swagger 接口文档格式损坏或未暴露' },
};

export const AbandonmentAttributionView: React.FC<AbandonmentAttributionViewProps> = ({
  abandonmentDistribution,
  onDiagnose,
  diagnosticResult: externalDiagnostic = null,
  loading = false,
  className = '',
}) => {
  const [inputPath, setInputPath] = useState('/docs/quickstart');
  const [inputContent, setInputContent] = useState('');
  const [hasLlmsTxt, setHasLlmsTxt] = useState(false);
  const [localDiagnostic, setLocalDiagnostic] = useState<AeoPageDiagnosticData | null>(null);
  const [isDiagnosing, setIsDiagnosing] = useState(false);

  const activeResult = externalDiagnostic || localDiagnostic;

  const handleRunDiagnosis = async () => {
    if (!onDiagnose || !inputContent.trim()) return;
    try {
      setIsDiagnosing(true);
      const res = await onDiagnose(inputPath, inputContent, hasLlmsTxt);
      setLocalDiagnostic(res);
    } finally {
      setIsDiagnosing(false);
    }
  };

  return (
    <div
      data-testid="abandonment-attribution-view"
      className={`p-5 rounded-xl border border-slate-800 bg-slate-900/90 space-y-5 ${className}`}
    >
      {/* 头部说明 */}
      <div className="pb-3 border-b border-slate-800 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-100">
            Agent 静默审判流失归因与 AEO 诊断 (Silent Judgment Attribution)
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            探究 AI Coding Agent 为什么在 400ms 内放弃你的产品并换用竞品
          </p>
        </div>
      </div>

      {/* 弃用原因排行榜 */}
      <div className="space-y-2">
        <h4 className="text-xs font-semibold text-slate-300">常见流失缺陷排行榜</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5" data-testid="reasons-ranking-grid">
          {Object.entries(abandonmentDistribution).map(([reasonKey, count]) => {
            const meta = REASON_DESC_MAP[reasonKey] || {
              label: reasonKey,
              desc: '其他未知 AEO 缺陷',
            };
            return (
              <div
                key={reasonKey}
                data-testid={`reason-card-${reasonKey}`}
                className="p-3 bg-slate-850 rounded-lg border border-slate-800 flex items-center justify-between"
              >
                <div className="space-y-0.5">
                  <div className="text-xs font-medium text-amber-300">{meta.label}</div>
                  <div className="text-[11px] text-slate-400">{meta.desc}</div>
                </div>
                <span className="font-mono font-bold text-slate-200 bg-slate-800 px-2 py-0.5 rounded text-xs">
                  {count} 次
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* 页面即时 AEO 诊断控制台 */}
      {onDiagnose && (
        <div className="p-4 bg-slate-950/60 rounded-xl border border-slate-800/80 space-y-3">
          <h4 className="text-xs font-semibold text-slate-200">页面 AEO 即时诊断实验场</h4>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">测试页面路径</label>
              <input
                type="text"
                data-testid="input-diagnostic-path"
                value={inputPath}
                onChange={(e) => setInputPath(e.target.value)}
                className="w-full px-2.5 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-slate-200 focus:outline-none focus:border-indigo-500 font-mono"
                placeholder="/docs/integration"
              />
            </div>
            <div className="flex items-center space-x-2 pt-5">
              <input
                type="checkbox"
                id="has-llms-txt"
                data-testid="input-has-llms-txt"
                checked={hasLlmsTxt}
                onChange={(e) => setHasLlmsTxt(e.target.checked)}
                className="rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-0"
              />
              <label htmlFor="has-llms-txt" className="text-xs text-slate-300">
                已在根目录配置 /llms.txt
              </label>
            </div>
          </div>

          <div>
            <label className="block text-[11px] text-slate-400 mb-1">页面 Markdown / HTML 原始内容</label>
            <textarea
              data-testid="input-diagnostic-content"
              value={inputContent}
              onChange={(e) => setInputContent(e.target.value)}
              rows={3}
              className="w-full px-2.5 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-slate-200 focus:outline-none focus:border-indigo-500 font-mono text-xs"
              placeholder="# 快速上手\n```python\nimport myrm\n```..."
            />
          </div>

          <button
            onClick={handleRunDiagnosis}
            disabled={isDiagnosing || loading || !inputContent.trim()}
            data-testid="run-diagnosis-btn"
            className="px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white transition flex items-center space-x-1.5"
          >
            {isDiagnosing ? <span>正在诊断...</span> : <span>立即运行 AEO 诊断</span>}
          </button>

          {/* 诊断结果报告展示 */}
          {activeResult && (
            <div
              data-testid="aeo-result-card"
              className="mt-3 p-3.5 bg-slate-900 rounded-lg border border-slate-800 space-y-2 text-xs"
            >
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-200">AEO 综合健康评分</span>
                <span
                  data-testid="aeo-score-badge"
                  className={`font-bold font-mono px-2 py-0.5 rounded text-xs ${
                    activeResult.aeo_score >= 80
                      ? 'bg-emerald-950/60 text-emerald-300 border border-emerald-800/60'
                      : activeResult.aeo_score >= 60
                      ? 'bg-amber-950/60 text-amber-300 border border-amber-800/60'
                      : 'bg-rose-950/60 text-rose-300 border border-rose-800/60'
                  }`}
                >
                  {activeResult.aeo_score} / 100
                </span>
              </div>

              <div className="text-[11px] text-slate-400">
                预估 Token 长度: <span className="text-slate-200 font-mono">{activeResult.estimated_tokens.toLocaleString()}</span> Tokens
                {activeResult.has_code_in_first_500_tokens ? ' ｜ ✓ 首屏示例完备' : ' ｜ ⚠️ 首屏无代码示例'}
              </div>

              <div className="space-y-1 pt-1">
                <div className="text-[11px] font-semibold text-slate-300">优化与修复建议：</div>
                {activeResult.suggested_actions.map((act, idx) => (
                  <div key={idx} className="text-[11px] text-indigo-300 flex items-start space-x-1">
                    <span className="text-indigo-400 font-mono">•</span>
                    <span>{act}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
