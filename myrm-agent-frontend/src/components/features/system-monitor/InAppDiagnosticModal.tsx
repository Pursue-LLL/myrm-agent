import React, { useState } from 'react';
import { DiagnosticBundle, TicketSubmitResponse } from './types';
import { SandboxSelfHealButton } from './SandboxSelfHealButton';

export interface InAppDiagnosticModalProps {
  isOpen: boolean;
  onClose: () => void;
  bundle: DiagnosticBundle;
  onTicketSubmitted?: (ticket: TicketSubmitResponse) => void;
}

export const InAppDiagnosticModal: React.FC<InAppDiagnosticModalProps> = ({
  isOpen,
  onClose,
  bundle,
  onTicketSubmitted,
}) => {
  const [description, setDescription] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [ticketResult, setTicketResult] = useState<TicketSubmitResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmitTicket = async () => {
    if (isSubmitting) return;

    setIsSubmitting(true);
    setError(null);

    try {
      const payload = {
        ...bundle,
        user_description: description.trim() || undefined,
      };

      const resp = await fetch('/api/v1/system/tickets/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        const errorData = await resp.json().catch(() => ({}));
        throw new Error(errorData.detail || `提交工单失败 (HTTP ${resp.status})`);
      }

      const ticket: TicketSubmitResponse = await resp.json();
      setTicketResult(ticket);
      onTicketSubmitted?.(ticket);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '未知工单提交异常';
      setError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 overflow-y-auto"
      data-testid="in-app-diagnostic-modal"
    >
      <div className="relative w-full max-w-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-900/50">
          <div className="flex items-center gap-2">
            <span className="text-xl">🩺</span>
            <div>
              <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
                端内沙箱现场全景诊断与闪电工单
              </h2>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                已自动封存故障现场快照与系统生命体征，保障运维极速闭环
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 p-1 rounded-lg"
            data-testid="modal-close-btn"
          >
            ✕
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-5 overflow-y-auto flex-1 text-sm">
          {/* Privacy & Integrity Pill */}
          <div className="flex items-center justify-between px-3.5 py-2.5 bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800 rounded-lg text-xs text-emerald-800 dark:text-emerald-300">
            <div className="flex items-center gap-2">
              <span className="text-sm">🛡️</span>
              <span>
                隐私安全保护已生效：已完成 <strong>{bundle.scrubbed_pii_count} 处</strong> API Key 与个人凭证严格脱敏掩码
              </span>
            </div>
            <span className="font-mono text-[10px] bg-emerald-100 dark:bg-emerald-900 px-2 py-0.5 rounded text-emerald-700 dark:text-emerald-200">
              HMAC 验真保护
            </span>
          </div>

          {/* Vitals Summary */}
          <div className="grid grid-cols-4 gap-3">
            <div className="p-3 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-100 dark:border-gray-800">
              <div className="text-[11px] text-gray-400">CPU 占用率</div>
              <div className="text-base font-bold text-gray-800 dark:text-gray-200 mt-1">
                {bundle.vitals.cpu_pct}%
              </div>
            </div>
            <div className="p-3 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-100 dark:border-gray-800">
              <div className="text-[11px] text-gray-400">内存使用率</div>
              <div
                className={`text-base font-bold mt-1 ${
                  bundle.vitals.mem_pct > 85 ? 'text-amber-500' : 'text-gray-800 dark:text-gray-200'
                }`}
              >
                {bundle.vitals.mem_pct}%
              </div>
            </div>
            <div className="p-3 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-100 dark:border-gray-800">
              <div className="text-[11px] text-gray-400">持久 Volume</div>
              <div className="text-base font-bold text-emerald-600 dark:text-emerald-400 mt-1">
                {bundle.vitals.is_volume_healthy ? '正常挂载' : '异常'}
              </div>
            </div>
            <div className="p-3 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-100 dark:border-gray-800">
              <div className="text-[11px] text-gray-400">网络连通态</div>
              <div className="text-base font-bold capitalize mt-1 text-gray-800 dark:text-gray-200">
                {bundle.vitals.network_state}
              </div>
            </div>
          </div>

          {/* Recent Logs Extract */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400 font-medium">
              <span>故障前现场捕获日志 ({bundle.logs.length} 条)</span>
              <span className="font-mono text-[10px]">Sandbox: {bundle.sandbox_id}</span>
            </div>
            <div className="bg-gray-950 text-gray-200 p-3 rounded-lg font-mono text-xs max-h-36 overflow-y-auto space-y-1 border border-gray-800">
              {bundle.logs.length === 0 ? (
                <div className="text-gray-500 italic">暂无现场异常日志</div>
              ) : (
                bundle.logs.map((log, idx) => (
                  <div key={idx} className="flex items-start gap-2 leading-relaxed">
                    <span
                      className={`text-[10px] px-1 py-0.5 rounded font-semibold shrink-0 ${
                        log.level === 'CRITICAL' || log.level === 'ERROR'
                          ? 'bg-red-900/60 text-red-300'
                          : log.level === 'WARN'
                          ? 'bg-amber-900/60 text-amber-300'
                          : 'bg-gray-800 text-gray-400'
                      }`}
                    >
                      {log.level}
                    </span>
                    <span className="text-gray-400 shrink-0 text-[10px]">[{log.subsystem}]</span>
                    <span className="break-all">{log.message}</span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Fast In-Place Reboot Self-Healing CTA */}
          <div className="p-3.5 bg-amber-50/60 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/50 rounded-lg">
            <div className="text-xs font-semibold text-amber-900 dark:text-amber-200 mb-2">
              无需等待人工？优先尝试原地热重启自愈
            </div>
            <SandboxSelfHealButton sandboxId={bundle.sandbox_id} />
          </div>

          {/* Ticket Response or Submission Form */}
          {ticketResult ? (
            <div
              className="p-4 bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-lg space-y-3"
              data-testid="ticket-dispatched-box"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-lg">⚡</span>
                  <span className="font-semibold text-blue-900 dark:text-blue-100">
                    闪电工单已分发：{ticketResult.ticket_id}
                  </span>
                </div>
                <span className="text-xs font-medium bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 px-2 py-0.5 rounded">
                  SLA 响应承诺 ≤ {ticketResult.sla_target_minutes} 分钟
                </span>
              </div>

              <div className="text-xs text-blue-800 dark:text-blue-200">
                <strong>智能初诊：</strong> {ticketResult.auto_diagnosis}
              </div>

              {ticketResult.suggested_actions.length > 0 && (
                <div className="text-xs text-blue-800 dark:text-blue-200 space-y-1">
                  <div className="font-semibold">自动化建议行动：</div>
                  <ul className="list-disc list-inside space-y-0.5 pl-1">
                    {ticketResult.suggested_actions.map((act, idx) => (
                      <li key={idx}>{act}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-3 pt-1">
              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                  补充故障现象说明（可选）
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="例如：在执行批量网页爬取时终端卡死在 85%，重试无效..."
                  rows={2}
                  className="w-full text-xs p-2.5 border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  data-testid="ticket-description-input"
                />
              </div>

              {error && (
                <div
                  className="text-xs p-2.5 rounded bg-red-50 dark:bg-red-950/30 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-900"
                  data-testid="ticket-error-msg"
                >
                  {error}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-3.5 border-t border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-900/50">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
          >
            {ticketResult ? '关闭' : '取消'}
          </button>

          {!ticketResult && (
            <button
              type="button"
              onClick={handleSubmitTicket}
              disabled={isSubmitting}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm disabled:opacity-60 transition-colors"
              data-testid="submit-ticket-btn"
            >
              {isSubmitting ? '正在封存提交工单...' : '一键提交闪电工单'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
