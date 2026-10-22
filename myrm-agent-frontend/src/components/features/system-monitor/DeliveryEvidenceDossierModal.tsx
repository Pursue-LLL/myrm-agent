/**
 * [INPUT]: isOpen, onClose, dossier (DeliveryEvidenceDossier).
 * [OUTPUT]: Modal rendering 5-dimension immutable task delivery evidence, physical test receipts, and .dossier.json exporter.
 * [POS]: myrm-agent-frontend/src/components/features/system-monitor/DeliveryEvidenceDossierModal.tsx
 */

import React from 'react';
import { DeliveryEvidenceDossier, UserAcceptanceStatus } from './deliveryDossierTypes';

export interface DeliveryEvidenceDossierModalProps {
  isOpen: boolean;
  onClose: () => void;
  dossier: DeliveryEvidenceDossier | null;
}

const ACCEPTANCE_BADGES: Record<UserAcceptanceStatus, { label: string; color: string }> = {
  ACCEPTED: {
    label: '✓ 直接采纳',
    color: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300 border-emerald-300 dark:border-emerald-700',
  },
  PARTIALLY_MODIFIED: {
    label: '⚡ 部分微调',
    color: 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300 border-amber-300 dark:border-amber-700',
  },
  REJECTED_REWORK: {
    label: '✕ 驳回返工',
    color: 'bg-red-100 text-red-800 dark:bg-red-950/60 dark:text-red-300 border-red-300 dark:border-red-700',
  },
};

export const DeliveryEvidenceDossierModal: React.FC<DeliveryEvidenceDossierModalProps> = ({
  isOpen,
  onClose,
  dossier,
}) => {
  if (!isOpen || !dossier) return null;

  const handleExportJson = () => {
    const blob = new Blob([JSON.stringify(dossier, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${dossier.dossier_id}.dossier.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const badgeConfig = ACCEPTANCE_BADGES[dossier.acceptance] || ACCEPTANCE_BADGES.ACCEPTED;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 overflow-y-auto"
      data-testid="delivery-dossier-modal"
    >
      <div className="relative w-full max-w-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-900/50">
          <div className="flex items-center gap-2">
            <span className="text-xl">📜</span>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
                  全链路任务交付证据卷宗
                </h2>
                <span
                  className={`px-2 py-0.5 text-[10px] font-bold border rounded-full ${badgeConfig.color}`}
                  data-testid="acceptance-badge"
                >
                  {badgeConfig.label}
                </span>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                不可变物化收据 · 物理验证测试退出码 · 交付物 SHA256 防篡改
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 p-1 rounded-lg"
            data-testid="dossier-close-btn"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto space-y-5 text-xs flex-1">
          {/* Metadata Banner */}
          <div className="grid grid-cols-3 gap-3 p-3 bg-gray-50 dark:bg-gray-800/40 border border-gray-100 dark:border-gray-800 rounded-lg">
            <div>
              <div className="text-[10px] text-gray-400">卷宗编号 (ID)</div>
              <div className="font-mono font-semibold text-gray-800 dark:text-gray-200 truncate mt-0.5" data-testid="dossier-id">
                {dossier.dossier_id}
              </div>
            </div>
            <div>
              <div className="text-[10px] text-gray-400">智能体模型指纹</div>
              <div className="font-mono text-gray-800 dark:text-gray-200 truncate mt-0.5" data-testid="agent-model">
                {dossier.persona.model_name}
              </div>
            </div>
            <div>
              <div className="text-[10px] text-gray-400">沉没摩擦消耗</div>
              <div className="font-semibold text-red-600 dark:text-red-400 mt-0.5" data-testid="wasted-tokens">
                {dossier.wasted_friction_tokens} Tokens (返工 {dossier.rework_count} 次)
              </div>
            </div>
          </div>

          {/* Dimension 1: Task Spec */}
          <div className="space-y-1.5 p-3 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg">
            <div className="font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-1.5">
              <span>🎯 事实维度 1: 需求 Spec 与验收准则</span>
            </div>
            <div className="text-gray-700 dark:text-gray-300 font-medium" data-testid="spec-goal">
              目标: {dossier.spec.task_goal}
            </div>
            <div className="flex flex-wrap gap-1.5 pt-1">
              {dossier.spec.acceptance_criteria.map((crit, idx) => (
                <span
                  key={idx}
                  className="px-2 py-0.5 bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300 rounded text-[11px]"
                >
                  ✓ {crit}
                </span>
              ))}
            </div>
          </div>

          {/* Dimension 2: Physical Verification Receipt */}
          <div className="space-y-1.5 p-3 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg">
            <div className="font-semibold text-gray-900 dark:text-gray-100 flex items-center justify-between">
              <span>🧪 事实维度 2: 客观物理验证收据</span>
              <span
                className={`px-2 py-0.5 font-mono text-[10px] font-bold rounded ${
                  dossier.verification.test_suite_exit_code === 0
                    ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300'
                    : 'bg-red-100 text-red-800 dark:bg-red-950/60 dark:text-red-300'
                }`}
                data-testid="exit-code-badge"
              >
                Exit Code: {dossier.verification.test_suite_exit_code}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-[11px] pt-1">
              <div className="text-gray-600 dark:text-gray-400">
                测试通过数: <strong className="text-emerald-600">{dossier.verification.passed_tests_count}</strong> 个 / 失败: {dossier.verification.failed_tests_count}
              </div>
              <div className="text-gray-600 dark:text-gray-400 truncate" title={dossier.verification.artifact_path}>
                物化产物: {dossier.verification.artifact_path}
              </div>
            </div>
            <div className="font-mono text-[10px] text-gray-400 truncate pt-1" title={dossier.verification.artifact_sha256}>
              SHA256: {dossier.verification.artifact_sha256}
            </div>
          </div>

          {/* Dimension 3: Tool Execution Traces */}
          <div className="space-y-1.5 p-3 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg">
            <div className="font-semibold text-gray-900 dark:text-gray-100">
              ⚡ 事实维度 3: 工具物化执行时序 ({dossier.tool_traces.length} 步)
            </div>
            <div className="max-h-28 overflow-y-auto space-y-1 pt-1 font-mono text-[11px]" data-testid="traces-list">
              {dossier.tool_traces.map((trace, idx) => (
                <div
                  key={idx}
                  className="flex justify-between items-center p-1.5 bg-gray-50 dark:bg-gray-800 rounded border border-gray-100 dark:border-gray-700/60"
                >
                  <span className="font-semibold text-blue-600 dark:text-blue-400">{trace.tool_name}</span>
                  <span className="truncate max-w-[200px] text-gray-600 dark:text-gray-300 px-2">{trace.arguments_summary}</span>
                  <span className="text-gray-400">{trace.duration_ms}ms</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-3 border-t border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-900/50">
          <div className="font-mono text-[10px] text-gray-400 truncate max-w-[260px]" title={dossier.dossier_checksum_sha256}>
            防篡改指纹: {dossier.dossier_checksum_sha256.slice(0, 16)}...
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleExportJson}
              className="px-3 py-1.5 bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg text-xs font-medium transition-colors"
              data-testid="export-dossier-json-btn"
            >
              导出 .dossier.json
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 bg-gray-200 hover:bg-gray-300 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg text-xs font-medium transition-colors"
              data-testid="modal-close-action-btn"
            >
              关闭
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
