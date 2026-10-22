import React, { useState } from 'react';
import type {
  CoverageSummaryResponse,
  ValidateSessionIdResponse,
  EntrypointType,
} from './unattendedCoverageTypes';

export interface UnattendedEventLogCoverageHUDProps {
  summary: CoverageSummaryResponse;
  onRefresh?: () => void;
  onValidate?: (entrypoint: EntrypointType, identifier: string) => Promise<ValidateSessionIdResponse>;
}

export const UnattendedEventLogCoverageHUD: React.FC<UnattendedEventLogCoverageHUDProps> = ({
  summary,
  onRefresh,
  onValidate,
}) => {
  const [selectedEntrypoint, setSelectedEntrypoint] = useState<EntrypointType>('cron');
  const [testIdentifier, setTestIdentifier] = useState('job_cleanup_daily');
  const [validationResult, setValidationResult] = useState<ValidateSessionIdResponse | null>(null);
  const [validating, setValidating] = useState(false);

  const handleValidate = async () => {
    if (!onValidate) return;
    setValidating(true);
    try {
      const res = await onValidate(selectedEntrypoint, testIdentifier);
      setValidationResult(res);
    } catch {
      // ignore
    } finally {
      setValidating(false);
    }
  };

  const totalShards = summary.shards.reduce((acc, s) => acc + s.file_count, 0);
  const totalBytes = summary.shards.reduce((acc, s) => acc + s.total_bytes, 0);

  return (
    <div
      data-testid="hud-unattended-coverage"
      className="p-4 bg-slate-900 border border-slate-800 rounded-xl text-slate-100 space-y-4"
    >
      {/* 顶部标题栏 */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            <span className="text-base font-semibold text-sky-400">
              无人值守与多渠道事件日志覆盖全景大盘
            </span>
            <span
              data-testid="anti-growth-badge"
              className="px-2 py-0.5 text-xs rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800"
            >
              防无限增长保护已激活
            </span>
          </div>
          <p className="text-xs text-slate-400">
            定时任务、IM 渠道、目标自主调度与语音调用统一事件日志防漏计与按日分片隔离
          </p>
        </div>
        {onRefresh && (
          <button
            type="button"
            data-testid="btn-refresh"
            onClick={onRefresh}
            className="px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
          >
            刷新状态
          </button>
        )}
      </div>

      {/* 核心指标卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="p-3 bg-slate-800/60 rounded-lg border border-slate-700/60 space-y-1">
          <div className="text-xs text-slate-400">日志根目录状态</div>
          <div
            data-testid="dir-status"
            className={`text-sm font-semibold ${
              summary.is_directory_configured ? 'text-emerald-400' : 'text-amber-400'
            }`}
          >
            {summary.is_directory_configured ? '已配置就绪' : '未配置 (Bypassed)'}
          </div>
          <div className="text-[10px] text-slate-500 truncate" title={summary.event_log_dir || 'None'}>
            {summary.event_log_dir || '无目录路径'}
          </div>
        </div>

        <div className="p-3 bg-slate-800/60 rounded-lg border border-slate-700/60 space-y-1">
          <div className="text-xs text-slate-400">单行最大字节阈值</div>
          <div className="text-sm font-semibold text-slate-200 font-mono">
            {summary.max_line_bytes ? `${Math.round(summary.max_line_bytes / 1024)} KB` : '系统默认'}
          </div>
          <div className="text-[10px] text-slate-500">超限行自动截断保护</div>
        </div>

        <div className="p-3 bg-slate-800/60 rounded-lg border border-slate-700/60 space-y-1">
          <div className="text-xs text-slate-400">受管入口覆盖率</div>
          <div className="text-sm font-semibold text-sky-400">
            {summary.entrypoints.filter((e) => e.is_injected).length} / {summary.entrypoints.length} 100%
          </div>
          <div className="text-[10px] text-slate-500">Cron / Channel / Goal / Voice</div>
        </div>

        <div className="p-3 bg-slate-800/60 rounded-lg border border-slate-700/60 space-y-1">
          <div className="text-xs text-slate-400">磁盘分片总数 / 占用</div>
          <div className="text-sm font-semibold text-purple-400 font-mono">
            {totalShards} 个 / {(totalBytes / 1024).toFixed(1)} KB
          </div>
          <div className="text-[10px] text-slate-500">按日分片无缝老化</div>
        </div>
      </div>

      {/* 入口覆盖策略明细表 */}
      <div className="space-y-2">
        <div className="text-xs font-medium text-slate-300">入口隔离与分片策略明细</div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left text-slate-300">
            <thead className="bg-slate-800/80 text-slate-400 uppercase text-[10px]">
              <tr>
                <th className="px-3 py-2">入口类型</th>
                <th className="px-3 py-2">注入状态</th>
                <th className="px-3 py-2">分片与隔离策略</th>
                <th className="px-3 py-2">生成会话标识样本</th>
                <th className="px-3 py-2">安全白名单</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {summary.entrypoints.map((spec) => (
                <tr
                  key={spec.entrypoint}
                  data-testid={`entrypoint-${spec.entrypoint}`}
                  className="hover:bg-slate-800/40"
                >
                  <td className="px-3 py-2 font-mono font-medium text-sky-300">{spec.entrypoint}</td>
                  <td className="px-3 py-2">
                    <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800">
                      已注入
                    </span>
                  </td>
                  <td className="px-3 py-2 text-slate-300">{spec.strategy_desc}</td>
                  <td className="px-3 py-2 font-mono text-[11px] text-slate-400">{spec.sample_session_id}</td>
                  <td className="px-3 py-2">
                    {spec.is_safe ? (
                      <span className="text-emerald-400 text-xs">通过 (Safe)</span>
                    ) : (
                      <span className="text-red-400 text-xs">拒绝 (Unsafe)</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 在线验证体验区 */}
      {onValidate && (
        <div className="p-3 bg-slate-800/40 rounded-lg border border-slate-700/50 space-y-2">
          <div className="text-xs font-medium text-slate-300">在线会话标识分片与安全校验</div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              data-testid="select-entrypoint"
              value={selectedEntrypoint}
              onChange={(e) => setSelectedEntrypoint(e.target.value as EntrypointType)}
              className="px-2 py-1 text-xs bg-slate-800 border border-slate-700 rounded text-slate-200"
            >
              <option value="cron">cron (定时任务)</option>
              <option value="channel">channel (IM 渠道)</option>
              <option value="goal">goal (自主目标)</option>
              <option value="voice">voice (语音Bridge)</option>
              <option value="voice_realtime">voice_realtime (实时语音)</option>
            </select>
            <input
              type="text"
              data-testid="input-identifier"
              value={testIdentifier}
              onChange={(e) => setTestIdentifier(e.target.value)}
              placeholder="输入任务 ID 或原始标识"
              className="px-2 py-1 text-xs bg-slate-800 border border-slate-700 rounded text-slate-200 font-mono w-48"
            />
            <button
              type="button"
              data-testid="btn-validate"
              onClick={handleValidate}
              disabled={validating}
              className="px-3 py-1 text-xs font-medium rounded bg-sky-600 hover:bg-sky-500 text-white transition disabled:opacity-50"
            >
              {validating ? '校验中...' : '生成与验证'}
            </button>
          </div>

          {validationResult && (
            <div
              data-testid="validation-result"
              className="mt-2 p-2 bg-slate-900/80 rounded border border-slate-800 text-xs font-mono space-y-1"
            >
              <div className="text-sky-400">
                解析会话标识: <span className="text-slate-200">{validationResult.resolved_session_id}</span>
              </div>
              <div className="flex items-center gap-4 text-[11px]">
                <span className={validationResult.is_safe ? 'text-emerald-400' : 'text-red-400'}>
                  白名单校验: {validationResult.is_safe ? '安全通过 (Safe)' : '违规拒绝 (Unsafe)'}
                </span>
                <span className={validationResult.is_daily_sharded ? 'text-purple-400' : 'text-slate-400'}>
                  按日分片: {validationResult.is_daily_sharded ? '已分片 (Daily Sharded)' : '无'}
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
