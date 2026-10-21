'use client';

import { useState, useCallback, useEffect } from 'react';
import { Database, ShieldAlert, Cpu, Sparkles, CheckCircle, RefreshCw } from 'lucide-react';

export interface McpSummaryArtifactData {
  artifact_id: string;
  source_tool_or_mcp: string;
  raw_payload_bytes: number;
  summary_bytes: number;
  token_saving_ratio: number;
  summary_text: string;
  extracted_fields: Record<string, string>;
  file_reference_path?: string | null;
  created_at: string;
}

export interface ContaminationReportData {
  risk_level: 'safe' | 'suspicious' | 'severe_contamination';
  payload_bytes: number;
  estimated_tokens: number;
  is_isolated_via_subagent: boolean;
  remediation_advice: string;
  detected_at: string;
}

export interface McpPayloadSummarizerCardProps {
  chatId?: string;
  initialArtifact?: McpSummaryArtifactData | null;
  initialReport?: ContaminationReportData | null;
  onApplySubagentPreset?: () => void;
  onDismiss?: () => void;
}

export function McpPayloadSummarizerCard({
  chatId,
  initialArtifact = null,
  initialReport = null,
  onApplySubagentPreset,
  onDismiss,
}: McpPayloadSummarizerCardProps) {
  const [artifact, setArtifact] = useState<McpSummaryArtifactData | null>(initialArtifact);
  const [report, setReport] = useState<ContaminationReportData | null>(initialReport);
  const [isLoading, setIsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'summary' | 'doctor' | 'preset'>('summary');
  const [presetSpec, setPresetSpec] = useState<{
    name: string;
    description: string;
    tools_whitelist: string[];
  } | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const fetchPresetSpec = useCallback(async () => {
    try {
      const res = await fetch('/api/agents/mcp-summarizer/preset');
      if (res.ok) {
        const json = await res.json();
        if (json.data) {
          setPresetSpec(json.data);
        }
      }
    } catch {
      setStatusMessage('获取预置子Agent规范失败');
    }
  }, []);

  useEffect(() => {
    void fetchPresetSpec();
  }, [fetchPresetSpec]);

  const handleSimulateSummary = async () => {
    setIsLoading(true);
    setStatusMessage(null);
    try {
      const dummyPayload = JSON.stringify({
        title: 'Figma Canvas Document Bulk Export',
        components: Array.from({ length: 40 }, (_, i) => ({
          id: `comp_${i}`,
          name: `Layer Component ${i}`,
          data: 'detailed properties and node trees '.repeat(8),
        })),
        metadata: { version: '2.0', source: 'figma-mcp' },
      });

      const res = await fetch('/api/agents/mcp-summarizer/summarize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_tool: 'figma_canvas_exporter',
          raw_payload: dummyPayload,
          target: {
            required_keys: ['title', 'components'],
            max_summary_tokens: 500,
            summarize_nested_lists_limit: 3,
          },
        }),
      });

      if (res.ok) {
        const json = await res.json();
        setArtifact(json.data);
        setStatusMessage('成功生成结构化摘要工件');
      } else {
        setStatusMessage('请求摘要失败');
      }
    } catch {
      setStatusMessage('网络请求异常');
    } finally {
      setIsLoading(false);
    }
  };

  const handleDiagnose = async () => {
    setIsLoading(true);
    setStatusMessage(null);
    try {
      const res = await fetch('/api/agents/mcp-summarizer/diagnose', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          raw_payload: 'x'.repeat(12000),
          is_isolated_via_subagent: false,
        }),
      });
      if (res.ok) {
        const json = await res.json();
        setReport(json.data);
      }
    } catch {
      setStatusMessage('诊断请求异常');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <dialog
      open
      aria-label="Heavy MCP Payload Summarizer Card"
      className="fixed bottom-6 right-6 z-50 m-0 w-96 rounded-xl border border-gray-200 bg-white/95 p-4 shadow-2xl backdrop-blur-md transition-all dark:border-gray-800 dark:bg-gray-900/95"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 pb-3 dark:border-gray-800">
        <div className="flex items-center gap-2">
          <Database className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
          <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            重 Payload MCP 摘要回传
          </h2>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => void fetchPresetSpec()}
            aria-label="刷新规范"
            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
          {onDismiss ? (
            <button
              type="button"
              onClick={onDismiss}
              aria-label="关闭"
              className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800"
            >
              ×
            </button>
          ) : null}
        </div>
      </div>

      {/* Tabs */}
      <div className="mt-2 flex border-b border-gray-100 text-xs font-medium dark:border-gray-800">
        <button
          type="button"
          onClick={() => setActiveTab('summary')}
          className={`flex-1 border-b-2 py-2 text-center transition-colors ${
            activeTab === 'summary'
              ? 'border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
              : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'
          }`}
        >
          结构化摘要
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('doctor')}
          className={`flex-1 border-b-2 py-2 text-center transition-colors ${
            activeTab === 'doctor'
              ? 'border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
              : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'
          }`}
        >
          污染审计
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('preset')}
          className={`flex-1 border-b-2 py-2 text-center transition-colors ${
            activeTab === 'preset'
              ? 'border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
              : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'
          }`}
        >
          专属子Agent
        </button>
      </div>

      {/* Tab Content */}
      <div className="mt-3 max-h-72 overflow-y-auto pr-1 text-xs">
        {activeTab === 'summary' ? (
          <div className="space-y-3">
            {artifact ? (
              <div className="rounded-lg border border-indigo-200 bg-indigo-50/40 p-2.5 dark:border-indigo-800 dark:bg-indigo-950/20">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-indigo-800 dark:text-indigo-300">
                    {artifact.source_tool_or_mcp}
                  </span>
                  <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-800 dark:bg-emerald-950 dark:text-emerald-400">
                    节省 {(artifact.token_saving_ratio * 100).toFixed(1)}% Tokens
                  </span>
                </div>
                <div className="mt-1.5 flex justify-between text-[11px] text-gray-500 dark:text-gray-400">
                  <span>原始: {(artifact.raw_payload_bytes / 1024).toFixed(1)} KB</span>
                  <span>摘要: {(artifact.summary_bytes / 1024).toFixed(1)} KB</span>
                </div>
                <div className="mt-2 rounded bg-white p-2 font-mono text-[10px] text-gray-700 shadow-inner dark:bg-gray-800 dark:text-gray-300">
                  <pre className="whitespace-pre-wrap">{artifact.summary_text}</pre>
                </div>
              </div>
            ) : (
              <div className="py-4 text-center text-gray-400">
                暂未捕获大 Payload 摘要工件
              </div>
            )}

            <button
              type="button"
              onClick={() => void handleSimulateSummary()}
              disabled={isLoading}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-indigo-600 py-2 font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
            >
              <Sparkles className="h-3.5 w-3.5" />
              <span>提取结构化摘要演练</span>
            </button>
          </div>
        ) : null}

        {activeTab === 'doctor' ? (
          <div className="space-y-3">
            <div className="rounded-lg bg-gray-50 p-2.5 dark:bg-gray-800/60">
              <span className="font-medium text-gray-700 dark:text-gray-300">
                Context Contamination 门禁规则
              </span>
              <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                主 Agent 直调大体积 MCP Payload 会常驻最长生命周期会话，严重击穿上下文窗口。
              </p>
            </div>

            {report ? (
              <div
                className={`rounded-lg border p-2.5 ${
                  report.risk_level === 'safe'
                    ? 'border-emerald-300 bg-emerald-50/60 dark:border-emerald-700 dark:bg-emerald-950/30'
                    : report.risk_level === 'suspicious'
                    ? 'border-amber-300 bg-amber-50/60 dark:border-amber-700 dark:bg-amber-950/30'
                    : 'border-red-300 bg-red-50/60 dark:border-red-700 dark:bg-red-950/30'
                }`}
              >
                <div className="flex items-center gap-1.5 font-semibold">
                  <ShieldAlert className="h-4 w-4" />
                  <span>
                    {report.risk_level === 'safe'
                      ? '上下文安全 (SAFE)'
                      : report.risk_level === 'suspicious'
                      ? '潜在污染警告 (SUSPICIOUS)'
                      : '严重上下文污染 (SEVERE)'}
                  </span>
                </div>
                <p className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">
                  {report.remediation_advice}
                </p>
              </div>
            ) : null}

            <button
              type="button"
              onClick={() => void handleDiagnose()}
              disabled={isLoading}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-amber-300 bg-amber-50 py-2 font-medium text-amber-700 transition-colors hover:bg-amber-100 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-400"
            >
              <Cpu className="h-3.5 w-3.5" />
              <span>检测当前会话污染风险</span>
            </button>
          </div>
        ) : null}

        {activeTab === 'preset' ? (
          <div className="space-y-3">
            {presetSpec ? (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-2.5 dark:border-gray-800 dark:bg-gray-800/40">
                <div className="flex items-center gap-1.5 font-semibold text-gray-800 dark:text-gray-200">
                  <CheckCircle className="h-4 w-4 text-emerald-600" />
                  <span>{presetSpec.name}</span>
                </div>
                <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                  {presetSpec.description}
                </p>
                <div className="mt-2 text-[11px]">
                  <span className="font-medium text-gray-700 dark:text-gray-300">工具白名单:</span>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {presetSpec.tools_whitelist.map((tool) => (
                      <span
                        key={tool}
                        className="rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
                      >
                        {tool}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}

            {onApplySubagentPreset ? (
              <button
                type="button"
                onClick={onApplySubagentPreset}
                className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-emerald-600 py-2 font-medium text-white transition-colors hover:bg-emerald-700"
              >
                <Sparkles className="h-3.5 w-3.5" />
                <span>一键绑定至当前会话</span>
              </button>
            ) : null}
          </div>
        ) : null}
      </div>

      {statusMessage ? (
        <div className="mt-2 text-center text-[11px] text-gray-500 dark:text-gray-400">
          {statusMessage}
        </div>
      ) : null}
    </dialog>
  );
}

export default McpPayloadSummarizerCard;
