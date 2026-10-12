/**
 * [INPUT]
 * Props: onSearch, searchResult, searching, onCopySnippet
 *
 * [OUTPUT]
 * FailureResolutionSearchView: Dual-track failure search and historical session resolution comparator.
 *
 * [POS]
 * Primary interactive view in FailureSessionRetrievalStudioCard.
 * Direct reading of historical solutions without guessing.
 * Strict typing applied: No `any` types allowed. Accessible form with htmlFor bindings. Single file < 380 lines.
 */

import React, { useState } from 'react';
import {
  Search,
  CheckCircle2,
  AlertOctagon,
  Copy,
  Terminal,
  ExternalLink,
  Info,
  Sparkles,
} from 'lucide-react';
import type {
  FailureRetrievalResultDTO,
  SearchFailureRequest,
} from '@/services/memory/failureSessionRetrieval';

export interface FailureResolutionSearchViewProps {
  onSearch: (request: SearchFailureRequest) => Promise<void>;
  searchResult: FailureRetrievalResultDTO | null;
  searching: boolean;
}

export const FailureResolutionSearchView: React.FC<FailureResolutionSearchViewProps> = ({
  onSearch,
  searchResult,
  searching,
}) => {
  const [toolName, setToolName] = useState<string>('run_command');
  const [errorMessage, setErrorMessage] = useState<string>(
    'Error: listen EADDRINUSE: address already in use :::8000',
  );
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handlePreset = (tool: string, error: string) => {
    setToolName(tool);
    setErrorMessage(error);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!errorMessage.trim()) return;
    await onSearch({
      tool_name: toolName.trim(),
      error_message: errorMessage.trim(),
      top_n: 3,
      include_cautionary: true,
    });
  };

  return (
    <div className="space-y-4">
      {/* 搜索表单与快速预设 */}
      <form onSubmit={handleSubmit} className="space-y-3 bg-card/60 p-4 rounded-lg border border-border">
        <div className="flex items-center justify-between">
          <div className="text-xs font-medium text-foreground flex items-center gap-1.5">
            <Search className="w-3.5 h-3.5 text-primary" />
            <span>输入工具报错实时检索历史会话同类解法</span>
          </div>

          {/* 预设报错快速载入 */}
          <div className="flex items-center gap-1.5 text-xs">
            <span className="text-muted-foreground">典型报错预设:</span>
            <button
              type="button"
              onClick={() =>
                handlePreset(
                  'run_command',
                  'Error: listen EADDRINUSE: address already in use :::8000',
                )
              }
              className="px-2 py-0.5 rounded text-xs bg-muted hover:bg-muted/80 text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
            >
              8000端口冲突
            </button>
            <button
              type="button"
              onClick={() =>
                handlePreset(
                  'git',
                  'remote: error: GH006: Protected branch update failed for refs/heads/main. Push rejected.',
                )
              }
              className="px-2 py-0.5 rounded text-xs bg-muted hover:bg-muted/80 text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
            >
              Git主干受限
            </button>
            <button
              type="button"
              onClick={() =>
                handlePreset(
                  'db_query',
                  'ERROR: deadlock detected on relation user_sessions while creating concurrent index',
                )
              }
              className="px-2 py-0.5 rounded text-xs bg-muted hover:bg-muted/80 text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
            >
              PG死锁超时
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div className="space-y-1">
            <label
              htmlFor="failure-tool-name-input"
              className="text-xs font-medium text-muted-foreground block"
            >
              执行工具名称
            </label>
            <input
              id="failure-tool-name-input"
              type="text"
              value={toolName}
              onChange={(e) => setToolName(e.target.value)}
              placeholder="如 run_command, bash, git"
              className="w-full px-2.5 py-1.5 text-xs bg-background rounded border border-input focus:outline-none focus:ring-2 focus:ring-primary text-foreground"
            />
          </div>

          <div className="md:col-span-3 space-y-1">
            <label
              htmlFor="failure-error-message-input"
              className="text-xs font-medium text-muted-foreground block"
            >
              原始错误日志 / 异常报错文本 (自动执行指纹提取与去噪)
            </label>
            <input
              id="failure-error-message-input"
              type="text"
              value={errorMessage}
              onChange={(e) => setErrorMessage(e.target.value)}
              placeholder="输入工具执行返回的真实报错信息..."
              className="w-full px-2.5 py-1.5 text-xs bg-background rounded border border-input focus:outline-none focus:ring-2 focus:ring-primary text-foreground"
            />
          </div>
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={searching || !errorMessage.trim()}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
          >
            <Search className={`w-3.5 h-3.5 ${searching ? 'animate-spin' : ''}`} />
            <span>{searching ? '匹配中...' : '提取指纹并检索历史解法'}</span>
          </button>
        </div>
      </form>

      {/* 检索结果展示 */}
      {searchResult && (
        <div className="space-y-4">
          {/* 规范化指纹与推荐动作 */}
          <div className="bg-muted/40 p-3 rounded-lg border border-border space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground font-medium">提取错误指纹:</span>
                <span className="px-2 py-0.5 text-xs rounded bg-destructive/10 text-destructive font-mono font-medium">
                  {searchResult.query_fingerprint.error_type}
                </span>
                <span className="text-xs text-muted-foreground">
                  (工具: {searchResult.query_fingerprint.tool_name || '通用'})
                </span>
              </div>
              <div className="flex items-center gap-1">
                {searchResult.query_fingerprint.context_tags.map((tag) => (
                  <span
                    key={tag}
                    className="px-1.5 py-0.5 text-[10px] rounded bg-muted text-muted-foreground border border-border"
                  >
                    #{tag}
                  </span>
                ))}
              </div>
            </div>

            {searchResult.suggested_action && (
              <div className="flex items-start gap-2 bg-primary/5 p-2 rounded border border-primary/20 text-xs text-foreground">
                <Sparkles className="w-4 h-4 text-primary shrink-0 mt-0.5" />
                <div>
                  <span className="font-semibold text-primary mr-1">建议解法动作:</span>
                  <span>{searchResult.suggested_action}</span>
                </div>
              </div>
            )}
          </div>

          {/* 双轨对比卡片：正向验证解法 vs 避坑死胡同反面教训 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* 1. 正向成功解决案例 */}
            <div className="space-y-2.5">
              <div className="flex items-center justify-between text-xs font-medium text-foreground">
                <div className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>正向验证解法 ({searchResult.successful_resolutions.length})</span>
                </div>
                <span className="text-[11px] text-muted-foreground">直读历史会话成功轮次</span>
              </div>

              {searchResult.successful_resolutions.length === 0 ? (
                <div className="p-4 text-center text-xs text-muted-foreground bg-muted/20 rounded-lg border border-dashed border-border">
                  暂无匹配的成功解法记录
                </div>
              ) : (
                searchResult.successful_resolutions.map((entry) => (
                  <div
                    key={entry.entry_id}
                    className="p-3 bg-emerald-500/5 rounded-lg border border-emerald-500/20 space-y-2"
                  >
                    <div className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-1.5">
                        <Terminal className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                        <span className="font-mono font-medium text-foreground">
                          {entry.session_id}
                        </span>
                        <span className="px-1.5 py-0.2 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-[10px]">
                          第 {entry.turn_index} 轮
                        </span>
                      </div>
                      <span className="text-[11px] text-muted-foreground">
                        置信度: {Math.round(entry.confidence * 100)}%
                      </span>
                    </div>

                    <div className="relative group">
                      <pre className="p-2 rounded bg-background border border-border text-xs font-mono text-emerald-600 dark:text-emerald-400 overflow-x-auto">
                        <code>{entry.solution_snippet}</code>
                      </pre>
                      <button
                        type="button"
                        onClick={() => handleCopy(entry.solution_snippet, entry.entry_id)}
                        className="absolute top-1.5 right-1.5 p-1 rounded bg-muted/80 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
                        title="复制解法命令"
                        aria-label="复制解法命令"
                      >
                        <Copy className="w-3 h-3" />
                      </button>
                    </div>

                    {copiedId === entry.entry_id && (
                      <div className="text-[10px] text-emerald-600 dark:text-emerald-400 font-medium">
                        已复制解法命令至剪贴板
                      </div>
                    )}

                    <p className="text-xs text-muted-foreground leading-relaxed">
                      {entry.explanation}
                    </p>
                  </div>
                ))
              )}
            </div>

            {/* 2. 避坑警示死胡同反面教训 */}
            <div className="space-y-2.5">
              <div className="flex items-center justify-between text-xs font-medium text-foreground">
                <div className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
                  <AlertOctagon className="w-4 h-4" />
                  <span>避坑死胡同警示 ({searchResult.cautionary_failures.length})</span>
                </div>
                <span className="text-[11px] text-muted-foreground">防范踩坑重复尝试</span>
              </div>

              {searchResult.cautionary_failures.length === 0 ? (
                <div className="p-4 text-center text-xs text-muted-foreground bg-muted/20 rounded-lg border border-dashed border-border">
                  暂无避坑警示记录
                </div>
              ) : (
                searchResult.cautionary_failures.map((entry) => (
                  <div
                    key={entry.entry_id}
                    className="p-3 bg-amber-500/5 rounded-lg border border-amber-500/20 space-y-2"
                  >
                    <div className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-1.5">
                        <AlertOctagon className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
                        <span className="font-mono font-medium text-foreground">
                          {entry.session_id}
                        </span>
                        <span className="px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[10px]">
                          踩坑尝试
                        </span>
                      </div>
                      <span className="text-[11px] text-muted-foreground">
                        置信度: {Math.round(entry.confidence * 100)}%
                      </span>
                    </div>

                    <pre className="p-2 rounded bg-background border border-border text-xs font-mono text-destructive line-through opacity-80 overflow-x-auto">
                      <code>{entry.solution_snippet}</code>
                    </pre>

                    <div className="flex items-start gap-1 text-xs text-amber-600 dark:text-amber-400 leading-relaxed">
                      <Info className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                      <span>{entry.explanation}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
