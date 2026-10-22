/**
 * [INPUT]: EvidenceCrossVerificationCockpitProps containing active finding, history, and triggers.
 * [OUTPUT]: EvidenceCrossVerificationCockpit React component visualizing 4-tier confidence proof and patches.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/EvidenceCrossVerificationCockpit.tsx
 */

import React, { useState } from 'react';
import {
  ConfidenceLevelEnum,
  EvidenceCrossVerificationCockpitProps,
  EvidenceItemData,
  EvidenceSourceTypeEnum,
  VerificationFindingData,
} from './evidenceCrossVerificationTypes';

export const EvidenceCrossVerificationCockpit: React.FC<EvidenceCrossVerificationCockpitProps> = ({
  activeFinding,
  recentDiagnoses = [],
  onDiagnose,
  onReset,
  isDiagnosing = false,
}) => {
  const [selectedErrorCode, setSelectedErrorCode] = useState<string>('ERR_GATEWAY_TIMEOUT');
  const [localFinding, setLocalFinding] = useState<VerificationFindingData | null>(
    activeFinding || null
  );

  const displayFinding = activeFinding || localFinding;

  const handleRunDiagnose = async () => {
    if (!onDiagnose) return;
    await onDiagnose(selectedErrorCode);
  };

  const getConfidenceBadge = (level: ConfidenceLevelEnum, score: number) => {
    switch (level) {
      case 'HIGH':
        return {
          text: `极高置信度 (${score}/4 分 · 建议采纳)`,
          cls: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400',
        };
      case 'MEDIUM':
        return {
          text: `中等置信度 (${score}/4 分 · 需人工复核)`,
          cls: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
        };
      case 'LOW':
      default:
        return {
          text: `低置信度 (${score}/4 分 · 仅供参考)`,
          cls: 'border-rose-500/40 bg-rose-500/10 text-rose-400',
        };
    }
  };

  const getSourceIcon = (source: EvidenceSourceTypeEnum) => {
    switch (source) {
      case 'KNOWLEDGE_BASE':
        return '📚 知识库历史';
      case 'CODE_SYMBOL':
        return '🔍 符号调用图谱';
      case 'SOURCE_LOGIC':
        return '⚙️ 源码逻辑分支';
      case 'RUNTIME_TELEMETRY':
        return '⏱️ 运行时Trace/日志';
      default:
        return '📋 证据项';
    }
  };

  return (
    <div className="flex flex-col space-y-6 rounded-xl border border-zinc-800 bg-zinc-950 p-6 text-zinc-100 shadow-xl">
      {/* 头部标题与排查动作栏 */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <div className="flex items-center space-x-3">
            <span className="text-xl font-bold tracking-tight text-white">
              多源证据交叉验证与四分制置信度排障大盘
            </span>
            <span className="rounded-md border border-indigo-500/30 bg-indigo-500/10 px-2.5 py-0.5 text-xs font-semibold text-indigo-300">
              四维立体现证引擎
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-400">
            静态代码 ＋ 分布式 Trace ＋ 运行时日志 ＋ 知识库历史深度印证 · 彻底杜绝“静态代码等于现场运行”的盲目推断
          </p>
        </div>

        <div className="flex items-center space-x-2">
          {onDiagnose && (
            <div className="flex items-center space-x-2">
              <input
                type="text"
                value={selectedErrorCode}
                onChange={(e) => setSelectedErrorCode(e.target.value)}
                placeholder="输入故障错误码..."
                className="w-48 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 focus:border-indigo-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={handleRunDiagnose}
                disabled={isDiagnosing}
                className="inline-flex items-center rounded-lg border border-indigo-500/40 bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
              >
                {isDiagnosing ? '排障推导中...' : '发起多源立体现证'}
              </button>
            </div>
          )}

          {onReset && (
            <button
              type="button"
              onClick={onReset}
              className="inline-flex items-center rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-700"
            >
              重置证据池
            </button>
          )}
        </div>
      </div>

      {/* 诊断结论核心卡片 */}
      {displayFinding ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
              <div className="text-xs font-medium text-zinc-400">故障错误码与语义</div>
              <div className="mt-2 text-lg font-bold text-white tracking-tight font-mono">
                {displayFinding.error_code}
              </div>
              <div className="mt-1 text-[11px] text-indigo-400 truncate">
                {displayFinding.resolved_code_meaning}
              </div>
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-zinc-400">四分制置信度评级</span>
              </div>
              <div className="mt-2">
                <span
                  className={`inline-block rounded-md border px-2.5 py-1 text-xs font-semibold ${
                    getConfidenceBadge(
                      displayFinding.confidence_level,
                      displayFinding.confidence_score
                    ).cls
                  }`}
                >
                  {
                    getConfidenceBadge(
                      displayFinding.confidence_level,
                      displayFinding.confidence_score
                    ).text
                  }
                </span>
              </div>
              <div className="mt-2 text-[11px] text-zinc-500">
                {displayFinding.bilateral_verified
                  ? '✓ 前后端双向调用契约验证通过'
                  : '⚠️ 未通过前后端双向逆向求证'}
              </div>
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
              <div className="text-xs font-medium text-zinc-400">根因类型定位</div>
              <div className="mt-2 text-lg font-bold text-amber-300 tracking-tight font-mono">
                {displayFinding.root_cause_category}
              </div>
              <div className="mt-1 text-[11px] text-zinc-500">
                区分内部累积超时 vs 下游阻塞
              </div>
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
              <div className="text-xs font-medium text-zinc-400">目标定位代码位置</div>
              <div className="mt-2 text-sm font-bold text-emerald-400 font-mono truncate">
                {displayFinding.target_file_path}:{displayFinding.target_line_number}
              </div>
              <div className="mt-1 text-[11px] text-zinc-500">
                精准锚定故障源头文件与行号
              </div>
            </div>
          </div>

          {/* 行动派交付修复建议卡片 */}
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-950/20 p-5">
            <div className="flex items-center space-x-2 border-b border-emerald-800/40 pb-3">
              <span className="text-sm font-bold text-emerald-300">
                🛠️ 行动派修复补丁建议 (Action-Oriented Patch)
              </span>
              <span className="rounded bg-emerald-500/20 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
                交付研发可直接采纳
              </span>
            </div>
            <div className="mt-3 text-xs text-zinc-300">
              <p className="mb-2 text-zinc-400">{displayFinding.explanation}</p>
              <pre className="overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-900/90 p-3 font-mono text-xs text-emerald-200">
                {displayFinding.recommended_patch}
              </pre>
            </div>
          </div>

          {/* 四维现证清单 */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-5">
            <h3 className="text-sm font-semibold text-zinc-200 border-b border-zinc-800 pb-3">
              📑 四维立体证据链 (Multi-Source Verification Proofs)
            </h3>
            {displayFinding.evidences.length === 0 ? (
              <div className="py-6 text-center text-xs text-zinc-500">暂无收集的证据项</div>
            ) : (
              <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                {displayFinding.evidences.map((ev, idx) => (
                  <div
                    key={idx}
                    className="flex flex-col justify-between rounded-lg border border-zinc-800/80 bg-zinc-900/70 p-3.5"
                  >
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-indigo-300">
                          {getSourceIcon(ev.source_type)}
                        </span>
                        <span className="rounded border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.2 text-[10px] text-emerald-400">
                          {ev.is_verified ? '已核验' : '待证实'}
                        </span>
                      </div>
                      <div className="mt-2 text-xs font-medium text-zinc-200">{ev.title}</div>
                      <p className="mt-1 text-[11px] text-zinc-400">{ev.detail}</p>
                    </div>

                    {(ev.file_path || ev.trace_id) && (
                      <div className="mt-3 border-t border-zinc-800/60 pt-2 text-[10px] font-mono text-zinc-500">
                        {ev.file_path && <span>路径: {ev.file_path}:{ev.line_number} </span>}
                        {ev.trace_id && <span>Span: {ev.trace_id}</span>}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="py-12 text-center text-xs text-zinc-500">
          暂无活跃排障结论，请输入错误码并发起多源立体现证
        </div>
      )}

      {/* 历史诊断卷宗列表 */}
      {recentDiagnoses.length > 0 && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
          <h3 className="text-sm font-semibold text-zinc-200 border-b border-zinc-800 pb-3">
            📜 最近排查诊断历史卷宗
          </h3>
          <div className="mt-3 space-y-2">
            {recentDiagnoses.map((item) => (
              <div
                key={item.diagnosis_id}
                onClick={() => setLocalFinding(item)}
                className="flex cursor-pointer items-center justify-between rounded-md border border-zinc-800/60 bg-zinc-900/60 px-3 py-2 text-xs transition-colors hover:border-zinc-700 hover:bg-zinc-800"
              >
                <div className="flex items-center space-x-3">
                  <span className="font-mono font-bold text-zinc-200">
                    {item.error_code}
                  </span>
                  <span className="text-zinc-400">
                    {item.root_cause_category}
                  </span>
                  <span className="font-mono text-zinc-500">
                    {item.target_file_path}:{item.target_line_number}
                  </span>
                </div>
                <div className="flex items-center space-x-2">
                  <span
                    className={`rounded border px-2 py-0.5 text-[10px] font-semibold ${
                      getConfidenceBadge(item.confidence_level, item.confidence_score).cls
                    }`}
                  >
                    {item.confidence_level} ({item.confidence_score}/4)
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
