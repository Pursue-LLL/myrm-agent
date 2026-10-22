import React, { useState } from 'react';
import type { SmartApproval } from './types';

interface SmartApprovalBannerProps {
  approval: SmartApproval | null;
  onApprove: (approvalId: string) => void;
  onDeny: (approvalId: string, reason: string) => void;
}

export const SmartApprovalBanner: React.FC<SmartApprovalBannerProps> = ({
  approval,
  onApprove,
  onDeny,
}) => {
  const [denyReason, setDenyReason] = useState<string>('高危命令，请改用非破坏性替代方案并重试');

  if (!approval) {
    return null;
  }

  const isPending = approval.status === 'pending';

  return (
    <div className="p-3 rounded-lg border border-amber-600/50 bg-amber-950/20 text-xs space-y-2 mt-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-amber-300">🛡️ Smart Approvals 独立命令审核</span>
          <span className="px-1.5 py-0.5 rounded text-[10px] bg-red-900/60 text-red-200 border border-red-700/50 font-mono">
            风险评分: {(approval.risk_score * 100).toFixed(0)}%
          </span>
        </div>
        <span className="text-[10px] text-zinc-400 font-mono">单次单命令授权，严格禁止永久放行</span>
      </div>

      <div className="bg-black/60 p-2 rounded border border-zinc-800 font-mono text-zinc-200 text-xs overflow-x-auto">
        <code>{approval.command}</code>
      </div>

      {approval.risk_reasons.length > 0 && (
        <ul className="list-disc list-inside text-amber-200/90 text-[11px] space-y-0.5">
          {approval.risk_reasons.map((reason, idx) => (
            <li key={idx}>{reason}</li>
          ))}
        </ul>
      )}

      {isPending ? (
        <div className="space-y-2 pt-1 border-t border-amber-800/40">
          <div className="flex items-center gap-2">
            <input
              type="text"
              aria-label="Deny reason input"
              value={denyReason}
              onChange={(e) => setDenyReason(e.target.value)}
              placeholder="输入 /deny 指导原因（用于子 Agent 自动自省重构）..."
              className="flex-1 bg-black/50 border border-zinc-700 rounded px-2 py-1 text-zinc-200 text-xs placeholder:text-zinc-500 focus:outline-none focus:border-amber-500"
            />
          </div>
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => onDeny(approval.approval_id, denyReason)}
              className="px-3 py-1 rounded bg-rose-900/70 hover:bg-rose-800 text-rose-200 border border-rose-700/60 font-medium transition-colors"
            >
              🛑 拒绝并反馈 (/deny)
            </button>
            <button
              type="button"
              onClick={() => onApprove(approval.approval_id)}
              className="px-3 py-1 rounded bg-emerald-800 hover:bg-emerald-700 text-emerald-100 border border-emerald-600/60 font-medium transition-colors"
            >
              ✅ 单次批准 (Approve Once)
            </button>
          </div>
        </div>
      ) : (
        <div className="pt-1 border-t border-zinc-800 text-[11px]">
          {approval.status === 'approved' ? (
            <span className="text-emerald-400 font-medium">
              ✅ 该命令已单次核准，消费后将自动失效以防越权。
            </span>
          ) : (
            <div className="space-y-1">
              <span className="text-rose-400 font-medium">
                🛑 该命令已被用户拒绝。已触发自省闭环，反馈 Prompt 已下发给子 Agent：
              </span>
              {approval.remediation_prompt && (
                <div className="p-1.5 rounded bg-black/40 border border-zinc-800 font-mono text-[10px] text-zinc-300">
                  {approval.remediation_prompt}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
