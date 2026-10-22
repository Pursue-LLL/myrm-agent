/**
 * [INPUT]: isOpen, onClose, initialLogs, initialTraces, onShareCreated.
 * [OUTPUT]: Interactive modal with zero-leak sanitized debug bundle preview, 48h ephemeral burn link creation, and .myrmdiag export.
 * [POS]: myrm-agent-frontend/src/components/features/system-monitor/SanitizedDebugShareModal.tsx
 */

import React, { useState } from 'react';
import { EphemeralShareLink, SanitizedDebugDump } from './sanitizedDebugTypes';

export interface SanitizedDebugShareModalProps {
  isOpen: boolean;
  onClose: () => void;
  rawLogs?: string[];
  recentTraces?: Record<string, string>[];
  onShareCreated?: (link: EphemeralShareLink) => void;
}

export const SanitizedDebugShareModal: React.FC<SanitizedDebugShareModalProps> = ({
  isOpen,
  onClose,
  rawLogs = [],
  recentTraces = [],
  onShareCreated,
}) => {
  const [userNote, setUserNote] = useState<string>('');
  const [isPackaging, setIsPackaging] = useState<boolean>(false);
  const [isGeneratingLink, setIsGeneratingLink] = useState<boolean>(false);
  const [dump, setDump] = useState<SanitizedDebugDump | null>(null);
  const [shareLink, setShareLink] = useState<EphemeralShareLink | null>(null);
  const [copied, setCopied] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'vitals' | 'logs' | 'audits'>('vitals');
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleGenerateDump = async () => {
    setIsPackaging(true);
    setError(null);
    try {
      const resp = await fetch('/api/v1/system/debug-share/dump', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          raw_logs: rawLogs,
          recent_traces: recentTraces,
          user_note: userNote,
        }),
      });

      if (!resp.ok) {
        throw new Error(`生成脱敏诊断包失败 (HTTP ${resp.status})`);
      }

      const result: SanitizedDebugDump = await resp.json();
      setDump(result);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '脱敏打包失败');
    } finally {
      setIsPackaging(false);
    }
  };

  const handleCreateShareLink = async () => {
    if (!dump) return;
    setIsGeneratingLink(true);
    setError(null);
    try {
      const resp = await fetch('/api/v1/system/debug-share/ephemeral-link', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dump_id: dump.dump_id,
        }),
      });

      if (!resp.ok) {
        throw new Error(`生成阅后即焚短链失败 (HTTP ${resp.status})`);
      }

      const link: EphemeralShareLink = await resp.json();
      setShareLink(link);
      onShareCreated?.(link);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '创建分享链接异常');
    } finally {
      setIsGeneratingLink(false);
    }
  };

  const handleCopyLink = () => {
    if (!shareLink) return;
    navigator.clipboard.writeText(shareLink.share_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadDiagnosticFile = () => {
    if (!dump) return;
    const blob = new Blob([JSON.stringify(dump, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${dump.dump_id}.myrmdiag`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 overflow-y-auto"
      data-testid="sanitized-debug-share-modal"
    >
      <div className="relative w-full max-w-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-900/50">
          <div className="flex items-center gap-2">
            <span className="text-xl">🛡️</span>
            <div>
              <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
                零外泄调试包导出与阅后即焚分享
              </h2>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                物理级密钥抹除脱敏 · 48h 阅后即焚自毁短链 · SHA256 完整性防篡改
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 p-1 rounded-lg"
            data-testid="modal-close-btn"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto space-y-5 text-sm flex-1">
          {error && (
            <div
              className="p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-lg text-xs text-red-600 dark:text-red-400"
              data-testid="error-alert"
            >
              {error}
            </div>
          )}

          {/* User note input */}
          {!dump && (
            <div className="space-y-2">
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300">
                附加排障备注 (将连同日志一并进行敏感词脱敏清洗):
              </label>
              <textarea
                value={userNote}
                onChange={(e) => setUserNote(e.target.value)}
                placeholder="描述异常发生时的上下文或错误提示..."
                rows={3}
                className="w-full px-3 py-2 text-xs border border-gray-300 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                data-testid="user-note-input"
              />
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={handleGenerateDump}
                  disabled={isPackaging}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors"
                  data-testid="generate-dump-btn"
                >
                  {isPackaging ? '物理脱敏与签名计算中...' : '生成零外泄诊断包'}
                </button>
              </div>
            </div>
          )}

          {/* Dump Preview Deck */}
          {dump && (
            <div className="space-y-4" data-testid="dump-preview-section">
              {/* Vitals & Redaction Summary Banner */}
              <div className="grid grid-cols-3 gap-3 p-3 bg-emerald-50/50 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-800/40 rounded-lg">
                <div className="text-center">
                  <div className="text-xs text-gray-500 dark:text-gray-400">已物理抹除敏感项</div>
                  <div className="text-lg font-bold text-emerald-600 dark:text-emerald-400" data-testid="redacted-count">
                    {dump.total_redacted_count} 项
                  </div>
                </div>
                <div className="text-center border-x border-emerald-200/50 dark:border-emerald-800/40">
                  <div className="text-xs text-gray-500 dark:text-gray-400">系统体征探针</div>
                  <div className="text-xs font-medium text-gray-800 dark:text-gray-200 mt-1">
                    {dump.vitals.os_name.split(' ')[0]} / Python {dump.vitals.python_version}
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-xs text-gray-500 dark:text-gray-400">SHA256 校验码</div>
                  <div className="text-[10px] font-mono text-gray-600 dark:text-gray-400 truncate mt-1 px-1" title={dump.checksum_sha256}>
                    {dump.checksum_sha256.slice(0, 12)}...
                  </div>
                </div>
              </div>

              {/* Navigation Tabs */}
              <div className="flex border-b border-gray-200 dark:border-gray-800 gap-4 text-xs font-medium">
                <button
                  type="button"
                  onClick={() => setActiveTab('vitals')}
                  className={`pb-2 ${
                    activeTab === 'vitals'
                      ? 'border-b-2 border-blue-600 text-blue-600 dark:text-blue-400'
                      : 'text-gray-500 hover:text-gray-700 dark:text-gray-400'
                  }`}
                  data-testid="tab-vitals"
                >
                  系统体征
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('logs')}
                  className={`pb-2 ${
                    activeTab === 'logs'
                      ? 'border-b-2 border-blue-600 text-blue-600 dark:text-blue-400'
                      : 'text-gray-500 hover:text-gray-700 dark:text-gray-400'
                  }`}
                  data-testid="tab-logs"
                >
                  脱敏日志 ({dump.sanitized_logs.length})
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('audits')}
                  className={`pb-2 ${
                    activeTab === 'audits'
                      ? 'border-b-2 border-blue-600 text-blue-600 dark:text-blue-400'
                      : 'text-gray-500 hover:text-gray-700 dark:text-gray-400'
                  }`}
                  data-testid="tab-audits"
                >
                  脱敏抹除审计 ({dump.redacted_audits.length})
                </button>
              </div>

              {/* Tab Content */}
              {activeTab === 'vitals' && (
                <div className="space-y-1 text-xs bg-gray-50 dark:bg-gray-800/40 p-3 rounded-lg border border-gray-100 dark:border-gray-800">
                  <div className="flex justify-between py-1 border-b border-gray-200/50 dark:border-gray-800/50">
                    <span className="text-gray-500">操作系统环境:</span>
                    <span className="font-mono text-gray-800 dark:text-gray-200">{dump.vitals.os_name}</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-gray-200/50 dark:border-gray-800/50">
                    <span className="text-gray-500">CPU 核心数 / 内存:</span>
                    <span className="font-mono text-gray-800 dark:text-gray-200">{dump.vitals.cpu_cores} 核 / {dump.vitals.memory_total_gb} GB</span>
                  </div>
                  <div className="flex justify-between py-1">
                    <span className="text-gray-500">网络连通状态:</span>
                    <span className="text-emerald-600 font-semibold">{dump.vitals.network_connectivity}</span>
                  </div>
                </div>
              )}

              {activeTab === 'logs' && (
                <div className="max-h-40 overflow-y-auto bg-gray-900 text-gray-200 p-3 rounded-lg font-mono text-[11px] space-y-1" data-testid="sanitized-logs-view">
                  {dump.sanitized_logs.length === 0 ? (
                    <div className="text-gray-500 italic">暂无日志内容</div>
                  ) : (
                    dump.sanitized_logs.map((log, idx) => (
                      <div key={idx} className="break-all">{log}</div>
                    ))
                  )}
                </div>
              )}

              {activeTab === 'audits' && (
                <div className="space-y-1 text-xs" data-testid="redacted-audits-view">
                  {dump.redacted_audits.length === 0 ? (
                    <div className="text-gray-500 italic p-2">未探测到需要脱敏的敏感凭证</div>
                  ) : (
                    dump.redacted_audits.map((a, idx) => (
                      <div key={idx} className="flex justify-between items-center p-2 bg-gray-50 dark:bg-gray-800 rounded border border-gray-100 dark:border-gray-700">
                        <span className="font-semibold text-gray-700 dark:text-gray-300">{a.rule_type}</span>
                        <div className="flex items-center gap-2">
                          <code className="text-[10px] bg-gray-200 dark:bg-gray-700 px-1 py-0.5 rounded text-gray-600 dark:text-gray-300">{a.masked_placeholder}</code>
                          <span className="text-red-500 font-bold">×{a.occurrences_count}</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}

              {/* Ephemeral Share Link Action */}
              <div className="p-3 bg-blue-50/40 dark:bg-blue-950/20 border border-blue-100 dark:border-blue-900/50 rounded-lg space-y-2">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs font-semibold text-gray-900 dark:text-gray-100">阅后即焚安全分享短链</div>
                    <div className="text-[11px] text-gray-500 dark:text-gray-400">默认 48 小时有效 · 限制 3 次阅读后自毁</div>
                  </div>
                  {!shareLink && (
                    <button
                      type="button"
                      onClick={handleCreateShareLink}
                      disabled={isGeneratingLink}
                      className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-xs font-medium transition-colors"
                      data-testid="create-ephemeral-link-btn"
                    >
                      {isGeneratingLink ? '生成中...' : '生成阅后即焚链接'}
                    </button>
                  )}
                </div>

                {shareLink && (
                  <div className="space-y-2 pt-1" data-testid="share-link-card">
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        readOnly
                        value={shareLink.share_url}
                        className="flex-1 px-2.5 py-1.5 text-xs font-mono bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded text-gray-800 dark:text-gray-200"
                        data-testid="share-url-input"
                      />
                      <button
                        type="button"
                        onClick={handleCopyLink}
                        className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 dark:bg-gray-700 dark:hover:bg-gray-600 text-white rounded text-xs font-medium transition-colors"
                        data-testid="copy-link-btn"
                      >
                        {copied ? '已复制' : '复制短链'}
                      </button>
                    </div>
                    <div className="flex justify-between text-[11px] text-gray-500 dark:text-gray-400">
                      <span>剩余查看配额: <strong className="text-blue-600">{shareLink.remaining_views}</strong> / {shareLink.max_views} 次</span>
                      <span>自毁状态: {shareLink.is_destroyed ? '已彻底销毁' : '正常活跃'}</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-3 border-t border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-900/50">
          <div className="text-[11px] text-gray-400">
            {dump ? `Dump ID: ${dump.dump_id}` : '零泄漏保证：密码、凭据与绝对系统路径均已替换'}
          </div>
          <div className="flex items-center gap-2">
            {dump && (
              <button
                type="button"
                onClick={handleDownloadDiagnosticFile}
                className="px-3 py-1.5 bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg text-xs font-medium transition-colors"
                data-testid="download-diag-file-btn"
              >
                导出 .myrmdiag 文件
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 bg-gray-200 hover:bg-gray-300 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg text-xs font-medium transition-colors"
              data-testid="footer-close-btn"
            >
              关闭
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
